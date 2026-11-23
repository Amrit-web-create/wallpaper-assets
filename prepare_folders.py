from pathlib import Path
from catalog_aliases import CATEGORY_ALIASES

WALLS_DIR = Path("walls")
PLACEHOLDER_NAME = "fake.page"


def main():
    WALLS_DIR.mkdir(parents=True, exist_ok=True)
    created_folders = 0
    created_placeholders = 0

    for category in sorted(CATEGORY_ALIASES.keys()):
        folder_name = category.strip().lower().replace(" ", "_")
        folder_path = WALLS_DIR / folder_name
        if not folder_path.exists():
            folder_path.mkdir(parents=True, exist_ok=True)
            created_folders += 1

        placeholder = folder_path / PLACEHOLDER_NAME
        if not placeholder.exists():
            placeholder.write_text(
                f"Placeholder for GitHub folder: {folder_name}\nUpload your .zip file here.\n",
                encoding="utf-8"
            )
            created_placeholders += 1

    print(f"Total categories in catalog: {len(CATEGORY_ALIASES)}")
    print(f"New folders created: {created_folders} | New fake.page files created: {created_placeholders}")


if __name__ == "__main__":
    main()
  
