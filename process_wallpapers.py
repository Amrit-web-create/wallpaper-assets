import json
import zipfile
from pathlib import Path
from urllib.parse import quote
from PIL import Image
from catalog_aliases import CATEGORY_ALIASES

BASE_URL = "https://your-wallpaper-assets.pages.dev/walls"
WALLS_DIR = Path("walls")
ZIPS_DIR = Path("incoming_zips")
OUT_JSON = Path("wallpapers.json")

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def extract_all_zips() -> int:
    WALLS_DIR.mkdir(parents=True, exist_ok=True)
    zip_candidates = list(Path(".").glob("*.zip"))
    if ZIPS_DIR.exists():
        zip_candidates.extend(ZIPS_DIR.glob("*.zip"))

    extracted_files = 0
    for zip_path in sorted(set(zip_candidates)):
        if not zip_path.is_file():
            continue
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                for member in zf.infolist():
                    if member.is_dir():
                        continue
                    rel = Path(member.filename)
                    if rel.is_absolute() or ".." in rel.parts:
                        print(f"[SKIP UNSAFE PATH] {member.filename}")
                        continue

                    parts = list(rel.parts)
                    if any(p.startswith("__MACOSX") or p == ".DS_Store" for p in parts):
                        continue
                    if parts and parts[0].lower() == "walls":
                        parts = parts[1:]
                    if not parts:
                        continue

                    dest = WALLS_DIR.joinpath(*parts)
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member) as src, open(dest, "wb") as dst:
                        dst.write(src.read())
                    extracted_files += 1

            zip_path.unlink(missing_ok=True)
            print(f"[EXTRACTED & DELETED ZIP] {zip_path}")
        except zipfile.BadZipFile:
            print(f"[INVALID ZIP SKIPPED] {zip_path}")

    return extracted_files


def verify_image(img_path: Path) -> bool:
    if not img_path.is_file() or img_path.stat().st_size <= 0:
        print(f"[EMPTY/MISSING FILE] {img_path}")
        return False
    if img_path.suffix.lower() not in IMAGE_EXTS:
        return False
    try:
        with Image.open(img_path) as im:
            im.verify()
        with Image.open(img_path) as im:
            w, h = im.size
            if w <= 0 or h <= 0:
                print(f"[INVALID DIMENSIONS] {img_path}")
                return False
        return True
    except Exception as exc:
        print(f"[CORRUPT IMAGE SKIPPED] {img_path} -> {exc}")
        return False


def build_tags(category: str, title: str) -> list[str]:
    cat_key = category.strip().lower()
    aliases = CATEGORY_ALIASES.get(cat_key, [])
    title_words = [w.lower() for w in title.replace("-", " ").replace("_", " ").split() if len(w) > 1]

    # Agar title ya category mein kisi aur god/category ka naam bhi aata hai, toh uske tags bhi jodein
    extra_aliases = set()
    searchable_text = f"{cat_key} {' '.join(title_words)}"
    for key, vals in CATEGORY_ALIASES.items():
        if key in searchable_text or any(v.lower() in searchable_text for v in vals if len(v) > 3):
            extra_aliases.add(key)
            extra_aliases.update(v.lower() for v in vals)

    combined = {cat_key, "wallpaper"} | {a.lower() for a in aliases} | set(title_words) | extra_aliases
    return sorted(combined)


def main():
    extracted = extract_all_zips()
    print(f"Extracted files from ZIPs: {extracted}")

    items = []
    idx = 1
    verified = 0
    skipped = 0

    if WALLS_DIR.exists():
        for folder in sorted(WALLS_DIR.iterdir()):
            if not folder.is_dir():
                continue

            category = folder.name.strip().lower()
            for file_path in sorted(folder.rglob("*")):
                if not file_path.is_file() or file_path.suffix.lower() not in IMAGE_EXTS:
                    continue

                if not verify_image(file_path):
                    skipped += 1
                    continue

                verified += 1
                rel_from_walls = file_path.relative_to(WALLS_DIR).as_posix()
                encoded_rel = "/".join(quote(part) for part in rel_from_walls.split("/"))

                clean_title = file_path.stem.replace("_", " ").replace("-", " ").strip().title()
                tags = build_tags(category, clean_title)

                items.append({
                    "id": str(idx),
                    "title": clean_title,
                    "category": category,
                    "tags": tags,
                    "url": f"{BASE_URL}/{encoded_rel}"
                })
                idx += 1

    OUT_JSON.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Verified: {verified} | Skipped: {skipped} | Total JSON items: {len(items)}")


if __name__ == "__main__":
    main()
    
