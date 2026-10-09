"""Shared DataForge cache contract for extraction and incremental diffing."""

from types import MappingProxyType

ENHANCEMENTS_GENERATION_CONTRACT_VERSION = 1

# Paths relative to ``libs/foundry/records`` that the persistent cache retains.
DATAFORGE_KEEP_SUBPATHS: tuple[str, ...] = (
    "entities/scitem",
    "entities/spaceships",
    "entities/groundvehicles",
    "entities/missions",
    "entities/contracts",
    "entities/jobterminal",
    "contracts/contractgenerator",
    "contracts/contracttemplates",
    "crafting/blueprintrewards",
    "crafting/blueprints/crafting",
    "resourcetypedatabase",
    "missionbroker/pu_missions",
    "ammoparams/vehicle",
    "ammoparams/fps",
    "reputation/rewards/missionrewards_reputation",
)

DATAFORGE_KEEP_FILE_GLOBS: tuple[str, ...] = ("actor/actors/argo_atls*.xml",)

# Paths relative to ``libs`` used to classify changed XML into generator jobs.
DATAFORGE_CATEGORY_SUBTREES = MappingProxyType(
    {
        "ships": (
            "foundry/records/entities/spaceships",
            "foundry/records/entities/scitem",
        ),
        "components": ("foundry/records/entities/scitem",),
        "ship_weapons": (
            "foundry/records/entities/scitem",
            "foundry/records/ammoparams/vehicle",
        ),
        "fps_weapons": (
            "foundry/records/entities/scitem",
            "foundry/records/ammoparams/fps",
        ),
        "missions": (
            "foundry/records/entities/scitem",
            "foundry/records/entities/spaceships",
            "foundry/records/entities/groundvehicles",
            "foundry/records/actor/actors/",
            "foundry/records/missionbroker/pu_missions",
            "foundry/records/entities/missions",
            "foundry/records/entities/contracts",
            "foundry/records/entities/jobterminal",
            "foundry/records/contracts/contractgenerator",
            "foundry/records/contracts/contracttemplates",
            "foundry/records/crafting/blueprintrewards",
            "foundry/records/crafting/blueprints/crafting",
            "foundry/records/reputation/rewards/missionrewards_reputation",
        ),
        "commodities": (
            "foundry/records/crafting/blueprints/crafting",
            "foundry/records/entities/scitem",
        ),
        "journal": (
            "foundry/records/crafting/blueprints/crafting",
            "foundry/records/entities/scitem",
        ),
    }
)
