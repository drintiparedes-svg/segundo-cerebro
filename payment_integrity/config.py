"""Configuración central del Payment Integrity Engine.

Todos los umbrales, pesos y parámetros del modelo viven aquí para que el
ajuste con data real no requiera tocar el código de las capas.
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class RuleThresholds:
    """Umbrales de la capa 2 (Rules Engine). Ajustables con data real."""

    # R01 — fracción de horas pagadas sin actividad clínica registrada
    max_idle_hours_ratio: float = 0.35
    # R02 — rendimiento observado mínimo como fracción del esperado
    min_performance_ratio: float = 0.50
    # R03 — n° de atenciones fuera del horario contratado tolerado por período
    max_off_schedule_encounters: int = 2
    # R04 — n° de pares de consultas con solapamiento tolerado por período
    max_overlapping_encounters: int = 0
    # R05 — n° de atenciones sin sesión (login) activa tolerado
    max_encounters_without_login: int = 1
    # R06 — n° de días con el mismo paciente contabilizado 2+ veces
    max_duplicate_patient_days: int = 1
    # R07 — fracción de días con horas pagadas > horas contratadas
    max_overpaid_days_ratio: float = 0.05
    # R08 — n° de pagos duplicados tolerado
    max_duplicate_payments: int = 0
    # R09 — fracción de bloques pagados íntegros sin ningún paciente atendido
    max_empty_paid_blocks_ratio: float = 0.05
    # R10 — fracción de la actividad concentrada en el primer/último cuarto del turno
    max_edge_concentration: float = 0.70
    # R11 — fracción de consultas con duración físicamente improbable (< min)
    improbable_duration_min: float = 4.0
    max_improbable_duration_ratio: float = 0.10
    # R12 — fracción de atenciones sin registro clínico asociado
    max_missing_record_ratio: float = 0.10
    # R13 — registro clínico creado retrospectivamente (horas después de la atención)
    retro_record_hours: float = 48.0
    max_retro_record_ratio: float = 0.10


@dataclass(frozen=True)
class PeerConfig:
    """Capa 3 — Provider Profiling (comparación contra pares clínicamente equivalentes)."""

    # Métricas comparadas contra el peer group con MAD z-score robusto
    metrics: tuple = (
        "patients_per_hour",
        "utilization",
        "cost_per_patient",
        "idle_hours_ratio",
        "mean_duration_min",
        "no_show_ratio",
    )
    # Dirección de riesgo de cada métrica: -1 = riesgo cuando es bajo, +1 = riesgo cuando es alto
    risk_direction: dict = field(
        default_factory=lambda: {
            "patients_per_hour": -1,
            "utilization": -1,
            "cost_per_patient": +1,
            "idle_hours_ratio": +1,
            "mean_duration_min": -1,
            "no_show_ratio": +1,
        }
    )
    # |z robusto| a partir del cual la desviación satura el score (percentil ~99.9)
    z_saturation: float = 3.5
    # Mínimo de pares para que la comparación sea estadísticamente honesta
    min_peer_size: int = 5


@dataclass(frozen=True)
class AnomalyConfig:
    """Capa 4 — Detección de anomalías no supervisada."""

    contamination: float = 0.06
    n_estimators: int = 400
    lof_neighbors: int = 15
    random_state: int = 42
    # z-scores robustos dentro del peer group (capa 3) + variables de integridad
    # independientes de la especialidad. Así el detector no confunde "oncología"
    # con "anomalía".
    features: tuple = (
        "patients_per_hour_z",
        "utilization_z",
        "cost_per_patient_z",
        "idle_hours_ratio_z",
        "mean_duration_min_z",
        "no_show_ratio_z",
        "performance_ratio",
        "paid_vs_contracted_ratio",
        "duplicate_payments",
        "off_schedule_encounters",
        "overlapping_encounters",
        "encounters_without_login",
        "duplicate_patient_days",
        "improbable_duration_ratio",
        "missing_record_ratio",
        "retro_record_ratio",
        "empty_paid_blocks_ratio",
        "edge_concentration",
    )
    # score de anomalía crudo → riesgo: 0 en mediana + k1·MAD, 1 en mediana + k2·MAD
    mad_k_low: float = 2.0
    mad_k_high: float = 6.0


@dataclass(frozen=True)
class ChangeConfig:
    """Capa E — Time-Series / Change Detection (médico contra sí mismo)."""

    ewma_alpha: float = 0.3
    # semanas iniciales usadas como línea base del propio médico
    baseline_weeks: int = 8
    # umbral CUSUM (en desviaciones estándar acumuladas) para señal de cambio
    cusum_threshold: float = 4.0
    cusum_drift: float = 0.5
    # caída relativa sostenida que satura el score (p. ej. -60 % vs histórico propio)
    drop_saturation: float = 0.60


@dataclass(frozen=True)
class GraphConfig:
    """Capa F — Graph Analytics (relaciones médico–paciente–tiempo)."""

    # minutos de tolerancia para considerar que dos atenciones al mismo paciente coinciden en el tiempo
    simultaneous_tolerance_min: float = 0.0
    # n° de atenciones simultáneas que satura el riesgo
    simultaneous_saturation: int = 6
    # fracción de pacientes compartidos que satura el riesgo (además del z robusto vs pares)
    shared_ratio_saturation: float = 0.50
    # visitas del mismo paciente en el mes a partir de las cuales se considera implausible
    max_visits_per_patient: int = 4
    # fracción de la cartera con visitas implausibles que satura el riesgo
    frequent_ratio_saturation: float = 0.25
    # atenciones por paciente en múltiplos de la mediana del grupo: riesgo desde 2× y saturación en 4×
    concentration_gate: float = 2.0
    # pacientes compartidos mínimos para que una arista cuente en la detección de comunidades
    community_min_shared: int = 3
    z_saturation: float = 3.5


@dataclass(frozen=True)
class ScoringConfig:
    """Capa 5 — Risk Scoring compuesto y clasificación por niveles."""

    weights: dict = field(
        default_factory=lambda: {
            "contract_risk": 0.18,   # conciliación contractual + pagos (R07, R08)
            "activity_risk": 0.22,   # horas sin actividad, bloques vacíos, registro clínico
            "productivity_risk": 0.18,  # rendimiento + cambio vs histórico propio
            "peer_risk": 0.18,       # desviación frente a pares equivalentes
            "anomaly_risk": 0.14,    # Isolation Forest + LOF
            "graph_risk": 0.10,      # relaciones médico–paciente (compartidos, simultáneos, concentración)
        }
    )
    # Cortes del score final (0-100) → niveles de la escala de gobernanza
    level_cuts: dict = field(
        default_factory=lambda: {
            0: (0, 20),    # Nivel 0 — normal
            1: (20, 40),   # Nivel 1 — anomalía operacional
            2: (40, 60),   # Nivel 2 — posible error administrativo
            3: (60, 75),   # Nivel 3 — posible pago indebido
            4: (75, 101),  # Nivel 4 — requiere auditoría
        }
    )
    # Escalamiento por reglas críticas: si una regla marcada ``critical`` alcanza
    # esta intensidad, el score se eleva al menos a ``critical_floor`` (nivel 3).
    # Evita que un caso con evidencia directa quede diluido por el promedio ponderado.
    critical_intensity: float = 0.5
    critical_floor: float = 60.0
    # atenciones simultáneas del mismo paciente con dos médicos: evidencia directa → escala como regla crítica
    graph_simultaneous_critical: int = 3
    level_labels: dict = field(
        default_factory=lambda: {
            0: "Normal",
            1: "Anomalía operacional",
            2: "Posible error administrativo",
            3: "Posible pago indebido",
            4: "Requiere auditoría",
        }
    )


@dataclass(frozen=True)
class SyntheticConfig:
    """Parámetros del generador de data proxy (reemplazable por data real)."""

    n_doctors: int = 60
    start_date: str = "2026-03-02"
    n_weeks: int = 26
    seed: int = 42
    # fracción de médicos con escenarios de riesgo inyectados (para validar el modelo)
    fraud_fraction: float = 0.15


@dataclass(frozen=True)
class EngineConfig:
    rules: RuleThresholds = field(default_factory=RuleThresholds)
    peer: PeerConfig = field(default_factory=PeerConfig)
    anomaly: AnomalyConfig = field(default_factory=AnomalyConfig)
    change: ChangeConfig = field(default_factory=ChangeConfig)
    graph: GraphConfig = field(default_factory=GraphConfig)
    scoring: ScoringConfig = field(default_factory=ScoringConfig)
    synthetic: SyntheticConfig = field(default_factory=SyntheticConfig)


DEFAULT_CONFIG = EngineConfig()
