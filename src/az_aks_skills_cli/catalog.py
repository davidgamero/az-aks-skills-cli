"""Read and validate a local skill index and its Markdown documents."""

import json
import os
from pathlib import Path


class CatalogError(Exception):
    pass


class Catalog:
    def __init__(self) -> None:
        default = Path(__file__).resolve().parents[2] / "skills"
        self.root = Path(os.environ.get("AZ_AKS_SKILLS_DIR", str(default))).resolve()
        try:
            data = json.loads((self.root / "index.json").read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError) as error:
            raise CatalogError(f"cannot read skill index: {error}") from error
        if not isinstance(data, dict) or data.get("version") != 1:
            raise CatalogError("skill index must have version 1")
        if not isinstance(data.get("skills"), list):
            raise CatalogError("skill index must contain a skills array")
        self.skills = data["skills"]
        seen = set()
        for skill in self.skills:
            if not isinstance(skill, dict) or any(
                not isinstance(skill.get(key), str) or not skill[key].strip()
                for key in ("id", "title", "description", "path")
            ):
                raise CatalogError("each skill needs nonempty id, title, description, path strings")
            if skill["id"] in seen:
                raise CatalogError(f"duplicate skill id: {skill['id']}")
            seen.add(skill["id"])
            if not isinstance(skill.get("tags"), list) or any(
                not isinstance(tag, str) for tag in skill["tags"]
            ):
                raise CatalogError(f"skill {skill['id']} needs a tags array of strings")
            self.document_path(skill)
        self.skills.sort(key=lambda skill: skill["id"])

    def document_path(self, skill: dict) -> Path:
        relative = Path(skill["path"])
        path = (self.root / relative).resolve()
        if relative.is_absolute() or not path.is_relative_to(self.root):
            raise CatalogError(f"skill {skill['id']} path must stay inside the catalog")
        if not path.is_file():
            raise CatalogError(f"skill {skill['id']} document is missing: {relative}")
        return path

    def content(self, skill: dict) -> str:
        try:
            return self.document_path(skill).read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            raise CatalogError(f"cannot read skill {skill['id']}: {error}") from error

    def get(self, name: str) -> dict:
        for skill in self.skills:
            if skill["id"] == name:
                return skill
        raise CatalogError(f"unknown skill: {name}; use 'az aks skill list' to see available skills")

    def search(self, query: str) -> list[dict]:
        terms = query.casefold().split()
        if not terms:
            raise CatalogError("search query must not be empty")
        matches = []
        for skill in self.skills:
            text = " ".join(
                [skill["id"], skill["title"], skill["description"], *skill["tags"]]
            ).casefold()
            if all(term in text for term in terms):
                matches.append(skill)
        return matches


def summary(skill: dict) -> dict:
    return {key: skill[key] for key in ("id", "title", "description", "tags")}
