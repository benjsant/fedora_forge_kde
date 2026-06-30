#!/usr/bin/env python3
"""Schema Pydantic pour le catalogue COPR experimental (depots tiers).

Les COPR sont des depots communautaires maintenus par des particuliers, NON
audites par Fedora ni par RPM Fusion : plus risques. Le catalogue impose donc un
avertissement global (experimental_warning) en plus de la liste des depots.
"""
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Format d'un identifiant COPR : owner/project (ex. atim/lazygit).
_COPR_ID = re.compile(r"^[\w.-]+/[\w.+-]+$")


class CoprRepo(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')

    id: str = Field(..., min_length=3)            # owner/project
    description: str = Field(..., min_length=1)   # fonctionnalite apportee
    packages: list[str] = Field(..., min_length=1)
    url: str = ""
    danger: str = ""                              # note de risque specifique (optionnel)

    @field_validator('id')
    @classmethod
    def validate_id(cls, v):
        if not _COPR_ID.match(v):
            raise ValueError(f"id COPR invalide : '{v}' (format attendu owner/project)")
        return v


class CoprCatalog(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')

    # Avertissement obligatoire : l'utilisateur installe a ses risques et perils.
    experimental_warning: str = Field(..., min_length=1)
    copr: list[CoprRepo] = Field(..., min_length=1)

    @field_validator('copr')
    @classmethod
    def validate_unique_ids(cls, v):
        ids = [c.id for c in v]
        dupes = [i for i in ids if ids.count(i) > 1]
        if dupes:
            raise ValueError(f"COPR en double : {', '.join(set(dupes))}")
        return v
