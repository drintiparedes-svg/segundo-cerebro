"""Generador de data proxy para el Payment Integrity Engine.

Produce las seis tablas del modelo de datos (ver README › Modelo de datos) con
comportamiento clínico plausible y escenarios de riesgo inyectados en una
fracción de médicos. La columna ``doctors.scenario`` existe SOLO para validar el
modelo; nunca se usa como feature ni estará disponible con data real.

Escenarios inyectados
---------------------
phantom_hours          horas pagadas íntegras con actividad concentrada en el primer 40 % del turno
productivity_collapse  historial normal y caída sostenida del rendimiento en las últimas 8 semanas
hours_overbilling      horas pagadas > contratadas de forma recurrente + pagos duplicados
ghost_records          atenciones sin registro clínico, duraciones improbables, paciente repetido
off_schedule           atenciones fuera del horario contratado, solapadas y sin sesión activa
network_billing        dos médicos comparten un pool reducido de pacientes con visitas frecuentes y
                       el mismo paciente aparece atendido por ambos en el mismo instante
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .config import SyntheticConfig

SCENARIOS = (
    "phantom_hours",
    "productivity_collapse",
    "hours_overbilling",
    "ghost_records",
    "off_schedule",
)
NETWORK_SCENARIO = "network_billing"   # siempre se inyecta en pareja

SPECIALTIES = {
    # especialidad: (rendimiento esperado pac/h, duración media min, valor hora CLP)
    "Medicina general": (4.0, 12.0, 30_000),
    "Pediatría": (3.5, 14.0, 32_000),
    "Medicina interna": (3.0, 17.0, 38_000),
    "Oncología médica": (2.5, 20.0, 45_000),
}
MODALITIES = ("presencial", "telemedicina")
SERVICE_TYPES = ("consulta", "control", "procedimiento_menor")


@dataclass
class SyntheticDataset:
    doctors: pd.DataFrame
    contracts: pd.DataFrame
    schedule: pd.DataFrame
    encounters: pd.DataFrame
    sessions: pd.DataFrame
    payments: pd.DataFrame

    def as_dict(self) -> dict[str, pd.DataFrame]:
        return {
            "doctors": self.doctors,
            "contracts": self.contracts,
            "schedule": self.schedule,
            "encounters": self.encounters,
            "sessions": self.sessions,
            "payments": self.payments,
        }


def _make_doctors(cfg: SyntheticConfig, rng: np.random.Generator) -> pd.DataFrame:
    n = cfg.n_doctors
    specialties = rng.choice(list(SPECIALTIES), size=n, p=[0.45, 0.2, 0.2, 0.15])
    modalities = rng.choice(MODALITIES, size=n, p=[0.65, 0.35])
    shifts = rng.choice(["diurno", "vespertino"], size=n, p=[0.7, 0.3])

    rows = []
    for i in range(n):
        base_rate, base_dur, base_rate_clp = SPECIALTIES[specialties[i]]
        # variación individual legítima del rendimiento (±15 %) y del valor hora (±10 %)
        rows.append(
            {
                "doctor_id": f"MED{i + 1:04d}",
                "specialty": specialties[i],
                "modality": modalities[i],
                "shift": shifts[i],
                "expected_rate": round(base_rate, 2),
                "own_rate": round(base_rate * rng.uniform(0.85, 1.15), 2),
                "own_duration_min": round(base_dur * rng.uniform(0.85, 1.15), 1),
                "hourly_rate": int(round(base_rate_clp * rng.uniform(0.9, 1.1), -2)),
                "scenario": "normal",
            }
        )
    doctors = pd.DataFrame(rows)
    doctors["peer_group"] = doctors["specialty"] + " | " + doctors["modality"]

    n_fraud = max(1, int(round(n * cfg.fraud_fraction)))
    fraud_idx = rng.choice(n, size=n_fraud, replace=False)
    if n_fraud >= 4:   # los dos últimos forman la red de facturación; el resto rota por los escenarios individuales
        solo, net = fraud_idx[:-2], fraud_idx[-2:]
        doctors.loc[solo, "scenario"] = [SCENARIOS[k % len(SCENARIOS)] for k in range(len(solo))]
        doctors.loc[net, "scenario"] = NETWORK_SCENARIO
        # la red comparte especialidad, modalidad y turno para que la comparación con pares sea honesta
        for col in ("specialty", "modality", "shift", "expected_rate"):
            doctors.loc[net[1], col] = doctors.loc[net[0], col]
        doctors["peer_group"] = doctors["specialty"] + " | " + doctors["modality"]
    else:
        doctors.loc[fraud_idx, "scenario"] = [SCENARIOS[k % len(SCENARIOS)] for k in range(n_fraud)]
    return doctors


def _weekdays(cfg: SyntheticConfig) -> pd.DatetimeIndex:
    start = pd.Timestamp(cfg.start_date)
    return pd.bdate_range(start, periods=cfg.n_weeks * 5)


def generate(cfg: SyntheticConfig | None = None) -> SyntheticDataset:
    cfg = cfg or SyntheticConfig()
    rng = np.random.default_rng(cfg.seed)
    doctors = _make_doctors(cfg, rng)
    days = _weekdays(cfg)
    # últimas 8 semanas (o la segunda mitad del período si la serie es más corta)
    collapse_start = days[max(0, len(days) - 40)] if len(days) > 2 else days[0]

    contracts, schedule, encounters, sessions, payments = [], [], [], [], []
    appt_seq = enc_seq = pay_seq = 0
    # la red de facturación comparte días de trabajo y un pool reducido de pacientes
    net_ids = doctors.loc[doctors["scenario"] == NETWORK_SCENARIO, "doctor_id"].tolist()
    net_work_days = set(rng.choice(5, size=4, replace=False))
    net_panel = rng.integers(10_000, 99_999, size=40)

    for doc in doctors.itertuples(index=False):
        # patrón semanal estable por médico: trabaja 3-5 días/semana
        work_days = set(rng.choice(5, size=int(rng.integers(3, 6)), replace=False))
        contracted_hours = int(rng.integers(4, 9))
        block_start_hour = 8 if doc.shift == "diurno" else 14
        # panel de pacientes propio (permite controles recurrentes legítimos)
        panel = rng.integers(10_000, 99_999, size=400)
        if doc.scenario == NETWORK_SCENARIO:
            work_days, panel, contracted_hours = net_work_days, net_panel, 6

        for day in days:
            if day.weekday() not in work_days:
                continue
            if rng.random() < 0.06:  # ausencias, licencias, capacitación
                continue

            c_start = day + pd.Timedelta(hours=block_start_hour)
            c_end = c_start + pd.Timedelta(hours=contracted_hours)
            contracts.append(
                {
                    "doctor_id": doc.doctor_id,
                    "date": day,
                    "contract_start": c_start,
                    "contract_end": c_end,
                    "contracted_hours": contracted_hours,
                }
            )

            # ---- agenda -------------------------------------------------------
            own_rate = doc.own_rate
            if doc.scenario == "productivity_collapse" and day >= collapse_start:
                own_rate *= 0.35
            n_slots = int(round(own_rate * contracted_hours * rng.uniform(0.9, 1.1)))
            n_slots = max(n_slots, 1)
            status = rng.choice(
                ["atendido", "ausente", "cancelado"], size=n_slots, p=[0.80, 0.13, 0.07]
            )
            patients = rng.choice(panel, size=min(n_slots, len(panel)), replace=False)
            if len(patients) < n_slots:
                patients = np.concatenate([patients, rng.choice(panel, size=n_slots - len(patients))])
            slot_minutes = np.sort(rng.uniform(0, contracted_hours * 60, size=n_slots))
            services = rng.choice(SERVICE_TYPES, size=n_slots, p=[0.55, 0.38, 0.07])

            for k in range(n_slots):
                appt_seq += 1
                schedule.append(
                    {
                        "appointment_id": f"AG{appt_seq:07d}",
                        "doctor_id": doc.doctor_id,
                        "patient_id": f"PAC{patients[k]}",
                        "date": day,
                        "slot_start": c_start + pd.Timedelta(minutes=float(slot_minutes[k])),
                        "status": status[k],
                        "service_type": services[k],
                    }
                )

            # ---- atenciones efectivas -------------------------------------------
            attended = np.where(status == "atendido")[0]
            n_att = len(attended)
            if n_att == 0:
                pay_hours = contracted_hours
                login = c_start - pd.Timedelta(minutes=float(rng.uniform(0, 15)))
                sessions.append(
                    {"doctor_id": doc.doctor_id, "date": day, "login_ts": login,
                     "logout_ts": c_end + pd.Timedelta(minutes=float(rng.uniform(0, 20)))}
                )
                pay_seq += 1
                payments.append(
                    {"payment_id": f"PG{pay_seq:07d}", "doctor_id": doc.doctor_id, "date": day,
                     "paid_hours": pay_hours, "hourly_rate": doc.hourly_rate,
                     "amount": pay_hours * doc.hourly_rate}
                )
                continue

            # ventana de actividad real dentro del turno
            active_window_min = contracted_hours * 60
            if doc.scenario == "phantom_hours":
                active_window_min = contracted_hours * 60 * 0.40

            # duraciones: lognormal alrededor de la duración propia del médico
            durations = rng.lognormal(np.log(doc.own_duration_min), 0.25, size=n_att)
            if doc.scenario == "ghost_records":
                improbable = rng.random(n_att) < 0.22
                durations[improbable] = rng.uniform(1.0, 3.0, size=improbable.sum())

            # secuencia temporal anclada a la hora agendada (los no-show dejan huecos
            # intercalados, no al final); se evita el solapamiento empujando el inicio
            slot_att = slot_minutes[attended] * (active_window_min / (contracted_hours * 60))
            starts = np.empty(n_att)
            prev_end = 0.0
            for j in range(n_att):
                st = max(float(slot_att[j]) + float(rng.uniform(-3, 8)), prev_end + float(rng.exponential(1.5)))
                starts[j] = max(st, 0.0)
                prev_end = starts[j] + durations[j]
            # si la secuencia se desborda de la ventana activa, se comprime proporcionalmente
            total_span = prev_end
            if total_span > active_window_min - 5:
                scale = (active_window_min - 5) / total_span
                starts *= scale
                durations *= scale          # el médico acorta consultas para caber en la ventana

            enc_patients = patients[attended]
            if doc.scenario == "ghost_records" and n_att >= 3:
                # mismo paciente contabilizado dos veces en el día
                dup = rng.integers(0, n_att, size=max(1, n_att // 6))
                enc_patients[dup] = enc_patients[rng.integers(0, n_att)]

            has_record = np.ones(n_att, dtype=bool)
            record_delay_h = rng.uniform(0.0, 6.0, size=n_att)
            if doc.scenario == "ghost_records":
                has_record &= rng.random(n_att) > 0.28
                retro = rng.random(n_att) < 0.15
                record_delay_h[retro] = rng.uniform(60, 240, size=retro.sum())

            login = c_start - pd.Timedelta(minutes=float(rng.uniform(0, 15)))
            last_end_min = float(starts[-1] + durations[-1])
            logout = c_start + pd.Timedelta(minutes=last_end_min + float(rng.uniform(5, 30)))
            logout = min(logout, c_end + pd.Timedelta(minutes=25))

            for j in range(n_att):
                st = c_start + pd.Timedelta(minutes=float(starts[j]))
                dur = float(durations[j])
                if doc.scenario == "off_schedule":
                    r = rng.random()
                    if r < 0.12:      # fuera del horario contratado (antes o después)
                        st = c_end + pd.Timedelta(minutes=float(rng.uniform(15, 120)))
                    elif r < 0.22 and j > 0:  # solapada con la anterior
                        st = c_start + pd.Timedelta(minutes=float(starts[j - 1] + 2))
                    elif r < 0.30:    # atención sin sesión activa (antes del login)
                        st = login - pd.Timedelta(minutes=float(rng.uniform(20, 60)))
                en = st + pd.Timedelta(minutes=dur)
                enc_seq += 1
                encounters.append(
                    {
                        "encounter_id": f"AT{enc_seq:07d}",
                        "doctor_id": doc.doctor_id,
                        "patient_id": f"PAC{enc_patients[j]}",
                        "date": day,
                        "start_ts": st,
                        "end_ts": en,
                        "duration_min": round(dur, 1),
                        "service_type": services[attended[j]],
                        "has_clinical_record": bool(has_record[j]),
                        "record_created_ts": en + pd.Timedelta(hours=float(record_delay_h[j]))
                        if has_record[j] else pd.NaT,
                    }
                )

            sessions.append(
                {"doctor_id": doc.doctor_id, "date": day, "login_ts": login, "logout_ts": logout}
            )

            # ---- pagos ---------------------------------------------------------------
            pay_hours = contracted_hours
            if doc.scenario == "hours_overbilling" and rng.random() < 0.40:
                pay_hours = contracted_hours + int(rng.integers(1, 4))
            pay_seq += 1
            payments.append(
                {"payment_id": f"PG{pay_seq:07d}", "doctor_id": doc.doctor_id, "date": day,
                 "paid_hours": pay_hours, "hourly_rate": doc.hourly_rate,
                 "amount": pay_hours * doc.hourly_rate}
            )
            if doc.scenario == "hours_overbilling" and rng.random() < 0.08:
                pay_seq += 1  # pago duplicado del mismo día
                payments.append(
                    {"payment_id": f"PG{pay_seq:07d}", "doctor_id": doc.doctor_id, "date": day,
                     "paid_hours": pay_hours, "hourly_rate": doc.hourly_rate,
                     "amount": pay_hours * doc.hourly_rate}
                )

    # ---- red de facturación: el mismo paciente aparece atendido por ambos médicos en el mismo instante
    if len(net_ids) >= 2:
        by_doc = {d: [e for e in encounters if e["doctor_id"] == d] for d in net_ids}
        for a in net_ids:
            for b in net_ids:
                if a == b:
                    continue
                src = by_doc[a]
                pick = rng.random(len(src)) < 0.08
                for e, take in zip(src, pick):
                    if take:
                        enc_seq += 1
                        encounters.append({**e, "encounter_id": f"AT{enc_seq:07d}", "doctor_id": b})

    return SyntheticDataset(
        doctors=doctors,
        contracts=pd.DataFrame(contracts),
        schedule=pd.DataFrame(schedule),
        encounters=pd.DataFrame(encounters),
        sessions=pd.DataFrame(sessions),
        payments=pd.DataFrame(payments),
    )
