from pathlib import Path
from catalog_aliases import CATEGORY_ALIASES

WALLPAPERS_ROOT = Path("wallpapers")
IMAGES_ROOT = Path("images")


def main():
    WALLPAPERS_ROOT.mkdir(parents=True, exist_ok=True)
    IMAGES_ROOT.mkdir(parents=True, exist_ok=True)

    for raw_key in sorted(CATEGORY_ALIASES.keys()):
        folder_name = raw_key.strip().lower().replace(" ", "_")

        wp_dir = WALLPAPERS_ROOT / folder_name
        wp_dir.mkdir(parents=True, exist_ok=True)
        wp_dummy = wp_dir / "fake.file"
        if not wp_dummy.exists():
            wp_dummy.write_text("Upload .zip files in this folder.\n", encoding="utf-8")

        img_dir = IMAGES_ROOT / folder_name
        img_dir.mkdir(parents=True, exist_ok=True)
        img_dummy = img_dir / "fake.imsge"
        if not img_dummy.exists():
            img_dummy.write_text("Upload direct image files (.jpg, .png, .webp) in this folder.\n", encoding="utf-8")

    print(f"Setup complete for {len(CATEGORY_ALIASES)} categories in 'wallpapers/' and 'images/'.")


if __name__ == "__main__":
    main()
  
