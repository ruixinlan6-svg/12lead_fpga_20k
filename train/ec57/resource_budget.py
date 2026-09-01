"""Single source of truth for the frozen M2 deployment resource budget."""

MODEL_DEPLOYMENT_PACKAGE_MAX_BYTES = 51_200
MODEL_PACKAGE_CONTAINER_OVERHEAD_RESERVE_BYTES = 1_024
MODEL_PARAMETER_PAYLOAD_MAX_BYTES = (
    MODEL_DEPLOYMENT_PACKAGE_MAX_BYTES
    - MODEL_PACKAGE_CONTAINER_OVERHEAD_RESERVE_BYTES
)
MODEL_MACS_PER_BEAT_MAX = 100_000
MODEL_MAX_ACTIVATION_BYTES = 2_048


def frozen_model_resource_limits():
    """Return a copy so callers cannot mutate the module-level contract."""
    return {
        "deployment_package_bytes": MODEL_DEPLOYMENT_PACKAGE_MAX_BYTES,
        "macs_per_beat": MODEL_MACS_PER_BEAT_MAX,
        "max_activation_bytes": MODEL_MAX_ACTIVATION_BYTES,
    }
