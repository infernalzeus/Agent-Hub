"""One question the model order asks of the learning layer: has the user let learning act (APPLY)? Kept here so agent_knowledge does not import the yard at module load."""


def apply_mode() -> bool:
    from ..yard import presets as P
    return P.mode() == "apply"
