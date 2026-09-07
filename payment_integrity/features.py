"""Construcción de variables derivadas (≈30) a nivel médico-día y médico-período.

Entrada: las tablas del modelo de datos (ver README › Modelo de datos).
Salida:  ``day_features`` (médico × día) y ``period_features`` (médico × mes).

Las tablas ``schedule`` y ``sessions`` son opcionales: si no existen, las
variables que dependen de ellas quedan en NaN y las reglas asociadas se omiten.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

BIN_MINUTES = 30  # resolución con la que se mide "hora con actividad"

REQUIRED = {
    "doctors": {"doctor_id", "peer_group", "expected_rate", "hourly_rate"},
    "contracts": {"doctor_id", "date", "contract_start", "contract_end", "contracted_hours"},
    "encounters": {"encounter_id", "doctor_id", "patient_id", "date", "start_ts", "end_ts"},
    "payments": {"payment_id", "doctor_id", "date", "paid_hours", "amount"},
}
OPTIONAL = {
    "schedule": {"doctor_id", "date", "status"},
    "sessions": {"doctor_id", "date", "login_ts", "logout_ts"},
}


def validate_inputs(data: dict[str, pd.DataFrame]) -> None:
    for table, cols in REQUIRED.items():
        if table not in data:
            raise ValueError(f"Falta la tabla obligatoria '{table}'")
        missing = cols - set(data[table].columns)
        if missing:
            raise ValueError(f"Tabla '{table}' sin columnas requeridas: {sorted(missing)}")
    for table, cols in OPTIONAL.items():
        if table in data and data[table] is not None:
            missing = cols - set(data[table].columns)
            if missing:
                raise ValueError(f"Tabla '{table}' sin columnas requeridas: {sorted(missing)}")


def _to_dt(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    df = df.copy()
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c])
    return df


def _nansum(s: pd.Series) -> float:
    """Suma que devuelve NaN (no 0) cuando la variable fuente no existe en la data."""
    return s.sum(min_count=1)


def _minutes(delta: pd.Series) -> pd.Series:
    return delta.dt.total_seconds() / 60.0


def _active_bins(enc: pd.DataFrame, paid_minutes_col: str) -> pd.Series:
    """N° de bloques de 30 min con al menos una atención dentro de la ventana pagada.

    Cada atención cubre un rango de bloques; los rangos se expanden de una vez con la
    técnica de repetición sobre índices, en vez de recorrer atención por atención.
    """
    if enc.empty:
        return pd.Series(dtype=float)
    off_s = np.maximum(enc["offset_start"].to_numpy(dtype=float), 0.0)
    off_e = np.minimum(enc["offset_end"].to_numpy(dtype=float), enc[paid_minutes_col].to_numpy(dtype=float))
    b0 = np.floor(np.nan_to_num(off_s, nan=0.0) / BIN_MINUTES).astype(np.int64)
    b1 = np.ceil(np.nan_to_num(off_e, nan=-1.0) / BIN_MINUTES).astype(np.int64)
    counts = np.maximum(b1 - b0, 0)
    total = int(counts.sum())
    if total == 0:
        return pd.Series(dtype=float)

    # rangos [b0, b1) concatenados sin bucle: desplazamiento local dentro de cada rango
    starts_rep = np.repeat(b0, counts)
    offsets = np.repeat(np.cumsum(counts) - counts, counts)
    bins = starts_rep + (np.arange(total) - offsets)

    tmp = pd.DataFrame({"doctor_id": np.repeat(enc["doctor_id"].to_numpy(), counts),
                        "date": np.repeat(enc["date"].to_numpy(), counts),
                        "bin": bins})
    return tmp.drop_duplicates().groupby(["doctor_id", "date"]).size()


def _half_window_concentration(offsets: np.ndarray, span: float) -> float:
    """Fracción de atenciones que cabe en la mitad contigua más cargada del turno."""
    n = offsets.size
    if n < 3 or not np.isfinite(span) or span <= 0:
        return np.nan
    half = span / 2.0
    windows = np.arange(0.0, span - half + 1e-9, 15.0)
    if windows.size == 0:
        return np.nan
    # matriz ventanas × atenciones: cuántas caen en cada ventana candidata
    inside = (offsets[None, :] >= windows[:, None]) & (offsets[None, :] < windows[:, None] + half)
    return float(inside.sum(axis=1).max()) / n


def build_day_features(data: dict[str, pd.DataFrame], improbable_min: float = 4.0,
                       retro_hours: float = 48.0) -> pd.DataFrame:
    validate_inputs(data)
    doctors = data["doctors"]
    contracts = _to_dt(data["contracts"], ["date", "contract_start", "contract_end"])
    enc = _to_dt(data["encounters"], ["date", "start_ts", "end_ts", "record_created_ts"])
    pay = _to_dt(data["payments"], ["date"])
    sched = _to_dt(data["schedule"], ["date"]) if data.get("schedule") is not None else None
    sess = _to_dt(data["sessions"], ["date", "login_ts", "logout_ts"]) if data.get("sessions") is not None else None

    key = ["doctor_id", "date"]

    # ---- pagos: horas pagadas, monto, duplicados ---------------------------------
    pay_day = pay.groupby(key).agg(
        paid_hours=("paid_hours", "sum"),
        total_paid=("amount", "sum"),
        n_payments=("payment_id", "count"),
    ).reset_index()
    pay_day["duplicate_payments"] = (pay_day["n_payments"] - 1).clip(lower=0)

    base = contracts.merge(pay_day, on=key, how="outer")
    base["contracted_hours"] = base["contracted_hours"].fillna(0.0)
    base["paid_hours"] = base["paid_hours"].fillna(0.0)
    base["total_paid"] = base["total_paid"].fillna(0.0)
    base["duplicate_payments"] = base["duplicate_payments"].fillna(0).astype(int)
    base["contract_minutes"] = base["contracted_hours"] * 60.0
    base["paid_minutes"] = base["paid_hours"] * 60.0
    base["overpaid_hours"] = (base["paid_hours"] - base["contracted_hours"]).clip(lower=0)
    base["overpaid_day"] = (base["overpaid_hours"] > 0).astype(int)
    base["paid_without_contract"] = (base["contract_start"].isna() & (base["paid_hours"] > 0)).astype(int)

    # ---- atenciones ----------------------------------------------------------------
    enc = enc.merge(base[key + ["contract_start", "contract_end", "contract_minutes", "paid_minutes"]],
                    on=key, how="left")
    enc["duration_min"] = _minutes(enc["end_ts"] - enc["start_ts"])
    enc["offset_start"] = _minutes(enc["start_ts"] - enc["contract_start"])
    enc["offset_end"] = _minutes(enc["end_ts"] - enc["contract_start"])
    enc["off_schedule"] = (
        enc["contract_start"].isna()
        | (enc["start_ts"] < enc["contract_start"])
        | (enc["start_ts"] >= enc["contract_end"])
    ).astype(int)
    enc = enc.sort_values(key + ["start_ts"])
    prev_end = enc.groupby(key)["end_ts"].shift(1)
    enc["overlapping"] = (enc["start_ts"] < prev_end - pd.Timedelta(minutes=1)).fillna(False).astype(int)
    enc["improbable_duration"] = (enc["duration_min"] < improbable_min).astype(int)

    if "has_clinical_record" in enc.columns:
        enc["missing_record"] = (~enc["has_clinical_record"].astype(bool)).astype(int)
    else:
        enc["missing_record"] = np.nan
    if "record_created_ts" in enc.columns:
        delay_h = (enc["record_created_ts"] - enc["end_ts"]).dt.total_seconds() / 3600.0
        enc["retro_record"] = ((delay_h > retro_hours) & enc["record_created_ts"].notna()).astype(int)
    else:
        enc["retro_record"] = np.nan

    if sess is not None:
        s = sess.groupby(key).agg(login_ts=("login_ts", "min"), logout_ts=("logout_ts", "max")).reset_index()
        enc = enc.merge(s, on=key, how="left")
        enc["without_login"] = (
            enc["login_ts"].isna() | (enc["start_ts"] < enc["login_ts"]) | (enc["start_ts"] > enc["logout_ts"])
        ).astype(int)
    else:
        enc["without_login"] = np.nan

    dup_pat = enc.groupby(key + ["patient_id"]).size().reset_index(name="n")
    dup_pat = dup_pat[dup_pat["n"] > 1].groupby(key).size().rename("duplicate_patients")

    enc_day = enc.groupby(key).agg(
        encounters=("encounter_id", "count"),
        unique_patients=("patient_id", "nunique"),
        mean_duration_min=("duration_min", "mean"),
        off_schedule_encounters=("off_schedule", "sum"),
        overlapping_encounters=("overlapping", "sum"),
        encounters_without_login=("without_login", _nansum),
        improbable_duration=("improbable_duration", "sum"),
        missing_record=("missing_record", _nansum),
        retro_record=("retro_record", _nansum),
        first_offset=("offset_start", "min"),
        last_offset=("offset_end", "max"),
    ).reset_index()
    enc_day = enc_day.merge(dup_pat.reset_index(), on=key, how="left")

    in_window = enc[enc["contract_start"].notna() & (enc["offset_end"] > 0)]
    active = _active_bins(in_window, "paid_minutes").rename("active_bins").reset_index()
    conc = (
        in_window.groupby(key, sort=False)
        .apply(lambda g: _half_window_concentration(g["offset_start"].to_numpy(dtype=float),
                                                    float(g["contract_minutes"].iloc[0])),
               include_groups=False)
        .rename("edge_concentration")
        .reset_index()
    )

    day = base.merge(enc_day, on=key, how="left").merge(active, on=key, how="left").merge(conc, on=key, how="left")
    for c in ["encounters", "unique_patients", "off_schedule_encounters", "overlapping_encounters",
              "improbable_duration", "duplicate_patients", "active_bins"]:
        day[c] = day[c].fillna(0)
    day["active_hours"] = np.minimum(day["active_bins"] * BIN_MINUTES / 60.0, day["paid_hours"])
    day["idle_hours"] = (day["paid_hours"] - day["active_hours"]).clip(lower=0)
    day["empty_paid_block"] = ((day["paid_hours"] > 0) & (day["encounters"] == 0)).astype(int)

    # ---- agenda (opcional) ---------------------------------------------------------
    if sched is not None:
        st = sched.groupby(key)["status"].value_counts().unstack(fill_value=0)
        st = st.rename(columns={"atendido": "attended_sched", "ausente": "no_show", "cancelado": "cancelled"})
        for c in ["attended_sched", "no_show", "cancelled"]:
            if c not in st.columns:
                st[c] = 0
        st["scheduled"] = st[["attended_sched", "no_show", "cancelled"]].sum(axis=1)
        day = day.merge(st.reset_index(), on=key, how="left")
        for c in ["scheduled", "no_show", "cancelled", "attended_sched"]:
            day[c] = day[c].fillna(0)
    else:
        day["scheduled"] = day["no_show"] = day["cancelled"] = day["attended_sched"] = np.nan

    day = day.merge(doctors[["doctor_id", "peer_group", "expected_rate", "hourly_rate"]], on="doctor_id", how="left")
    day["patients_attended"] = day["encounters"]
    day["period"] = day["date"].dt.to_period("M").astype(str)
    day["week"] = day["date"].dt.to_period("W").dt.start_time
    return day


def build_period_features(day: pd.DataFrame) -> pd.DataFrame:
    """Agrega médico × día a médico × mes y deriva las ratios del modelo."""
    g = day.groupby(["doctor_id", "period"])
    p = g.agg(
        peer_group=("peer_group", "first"),
        expected_rate=("expected_rate", "first"),
        hourly_rate=("hourly_rate", "first"),
        days_worked=("date", "nunique"),
        contracted_hours=("contracted_hours", "sum"),
        paid_hours=("paid_hours", "sum"),
        total_paid=("total_paid", "sum"),
        active_hours=("active_hours", "sum"),
        idle_hours=("idle_hours", "sum"),
        patients_attended=("patients_attended", "sum"),
        unique_patients=("unique_patients", "sum"),
        scheduled=("scheduled", "sum"),
        no_show=("no_show", "sum"),
        cancelled=("cancelled", "sum"),
        mean_duration_min=("mean_duration_min", "mean"),
        off_schedule_encounters=("off_schedule_encounters", "sum"),
        overlapping_encounters=("overlapping_encounters", "sum"),
        encounters_without_login=("encounters_without_login", _nansum),
        duplicate_patient_days=("duplicate_patients", lambda s: int((s > 0).sum())),
        overpaid_days=("overpaid_day", "sum"),
        overpaid_hours=("overpaid_hours", "sum"),
        paid_without_contract_days=("paid_without_contract", "sum"),
        duplicate_payments=("duplicate_payments", "sum"),
        empty_paid_blocks=("empty_paid_block", "sum"),
        edge_concentration=("edge_concentration", "mean"),
        improbable_duration=("improbable_duration", "sum"),
        missing_record=("missing_record", _nansum),
        retro_record=("retro_record", _nansum),
    ).reset_index()

    ph = p["paid_hours"].replace(0, np.nan)
    att = p["patients_attended"].replace(0, np.nan)
    p["patients_per_hour"] = (p["patients_attended"] / ph).fillna(0.0)
    p["performance_ratio"] = p["patients_per_hour"] / p["expected_rate"]
    p["utilization"] = (p["active_hours"] / ph).fillna(0.0)
    p["idle_hours_ratio"] = (p["idle_hours"] / ph).fillna(1.0)
    p["cost_per_patient"] = (p["total_paid"] / att).fillna(p["total_paid"])
    p["no_show_ratio"] = p["no_show"] / p["scheduled"].replace(0, np.nan)
    p["overpaid_days_ratio"] = p["overpaid_days"] / p["days_worked"]
    p["empty_paid_blocks_ratio"] = p["empty_paid_blocks"] / p["days_worked"]
    p["improbable_duration_ratio"] = (p["improbable_duration"] / att).fillna(0.0)
    p["missing_record_ratio"] = p["missing_record"] / att
    p["retro_record_ratio"] = p["retro_record"] / att
    p["paid_vs_contracted_ratio"] = p["paid_hours"] / p["contracted_hours"].replace(0, np.nan)
    p["expected_paid"] = p["contracted_hours"] * p["hourly_rate"]
    return p


PERIOD_FEATURE_DICTIONARY = {
    "days_worked": "Días con contrato o pago en el período",
    "contracted_hours": "Horas contratadas (suma de bloques)",
    "paid_hours": "Horas efectivamente pagadas (incluye duplicados)",
    "total_paid": "Monto pagado en CLP",
    "active_hours": "Horas con actividad clínica registrada (bloques de 30 min)",
    "idle_hours": "Horas pagadas sin actividad clínica registrada",
    "idle_hours_ratio": "R1 del documento: horas sin actividad / horas pagadas",
    "utilization": "Horas con actividad / horas pagadas",
    "patients_attended": "Atenciones efectivas registradas",
    "patients_per_hour": "Rendimiento observado (pacientes / hora pagada)",
    "performance_ratio": "Rendimiento observado / rendimiento esperado",
    "cost_per_patient": "Pago total / pacientes atendidos",
    "no_show_ratio": "Pacientes ausentes / agendados",
    "mean_duration_min": "Duración media de la consulta",
    "off_schedule_encounters": "Atenciones fuera del horario contratado",
    "overlapping_encounters": "Atenciones solapadas en el tiempo",
    "encounters_without_login": "Atenciones sin sesión (login) activa",
    "duplicate_patient_days": "Días con el mismo paciente contabilizado 2+ veces",
    "overpaid_days_ratio": "Fracción de días con horas pagadas > contratadas",
    "duplicate_payments": "Pagos duplicados detectados",
    "empty_paid_blocks_ratio": "Fracción de bloques pagados íntegros sin pacientes",
    "edge_concentration": "Fracción de la actividad en la mitad más cargada del turno",
    "improbable_duration_ratio": "Fracción de consultas con duración físicamente improbable",
    "missing_record_ratio": "Fracción de atenciones sin registro clínico",
    "retro_record_ratio": "Fracción de registros clínicos creados retrospectivamente",
    "paid_vs_contracted_ratio": "Horas pagadas / horas contratadas",
}
