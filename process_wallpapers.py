import json
import zipfile
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import quote
from PIL import Image
from catalog_aliases import CATEGORY_ALIASES

BASE_URL = "https://wallpaper-assets-5l7.pages.dev/walls"
WALLS_DIR = Path("walls")
ZIPS_DIR = Path("incoming_zips")
OUT_JSON = Path("wallpapers.json")

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
IGNORE_FILENAMES = {"fake.page", ".gitkeep", ".ds_store", "thumbs.db"}
SIMILARITY_THRESHOLD = 0.65


def similarity(a: str, b: str) -> float:
    a_clean = a.strip().lower()
    b_clean = b.strip().lower()
    if not a_clean or not b_clean:
        return 0.0
    if a_clean == b_clean:
        return 1.0
    if len(a_clean) >= 4 and len(b_clean) >= 4 and (a_clean in b_clean or b_clean in a_clean):
        return 0.85
    return SequenceMatcher(None, a_clean, b_clean).ratio()


def match_best_category(raw_text: str) -> tuple[str, list[str]]:
    cleaned = raw_text.replace("_", " ").replace("-", " ").strip().lower()
    if cleaned in CATEGORY_ALIASES:
        return cleaned, CATEGORY_ALIASES[cleaned]

    best_key = cleaned
    best_score = 0.0
    tokens = [t for t in cleaned.split() if len(t) >= 3] + [cleaned]

    for key, aliases in CATEGORY_ALIASES.items():
        candidates = [key] + [a.lower() for a in aliases]
        for token in tokens:
            for cand in candidates:
                score = similarity(token, cand)
                if score > best_score:
                    best_score = score
                    best_key = key

    if best_score >= SIMILARITY_THRESHOLD:
        return best_key, CATEGORY_ALIASES.get(best_key, [])

    return cleaned or "general", []


def extract_single_zip(zip_path: Path, folder_hint: str | None) -> int:
    extracted_images = 0
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
                if any(p.startswith("__MACOSX") or p.lower() in IGNORE_FILENAMES for p in parts):
                    continue

                file_name = parts[-1]
                ext = Path(file_name).suffix.lower()
                if ext not in IMAGE_EXTS:
                    continue

                target_cat = (folder_hint or "general").strip().lower().replace(" ", "_")
                matched_cat, _ = match_best_category(target_cat)
                final_folder = matched_cat if matched_cat != "general" else target_cat

                # Zip ke andar jitni bhi images hain, unhe clean tareeke se final_folder mein daalein
                dest = WALLS_DIR / final_folder / file_name
                if dest.exists():
                    stem = Path(file_name).stem
                    counter = 1
                    while (WALLS_DIR / final_folder / f"{stem}_{counter}{ext}").exists():
                        counter += 1
                    dest = WALLS_DIR / final_folder / f"{stem}_{counter}{ext}"

                dest.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member) as src, open(dest, "wb") as dst:
                    dst.write(src.read())
                extracted_images += 1

        zip_path.unlink(missing_ok=True)
        print(f"[EXTRACTED & REMOVED ZIP] {zip_path} -> {extracted_images} images")
    except zipfile.BadZipFile:
        print(f"[INVALID ZIP SKIPPED] {zip_path}")

    return extracted_images


def extract_all_zips() -> int:
    WALLS_DIR.mkdir(parents=True, exist_ok=True)
    total_extracted = 0

    if WALLS_DIR.exists():
        for sub in sorted(WALLS_DIR.iterdir()):
            if sub.is_dir():
                for zp in sorted(sub.rglob("*.zip")):
                    if zp.is_file():
                        total_extracted += extract_single_zip(zp, folder_hint=sub.name)

    extra_zips = list(Path(".").glob("*.zip"))
    if ZIPS_DIR.exists():
        extra_zips.extend(ZIPS_DIR.rglob("*.zip"))

    for zp in sorted(set(extra_zips)):
        if zp.is_file():
            hint = zp.parent.name if zp.parent != Path(".") else None
            total_extracted += extract_single_zip(zp, folder_hint=hint)

    return total_extracted


def verify_image(img_path: Path) -> bool:
    if img_path.name.lower() in IGNORE_FILENAMES:
        return False
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


def build_tags(raw_category: str, title: str) -> tuple[str, list[str]]:
    matched_cat, primary_aliases = match_best_category(raw_category)
    title_matched_cat, title_aliases = match_best_category(title)

    final_category = matched_cat if matched_cat != "general" else title_matched_cat
    title_words = [w.lower() for w in title.replace("-", " ").replace("_", " ").split() if len(w) > 1]

    extra_aliases = set()
    searchable_text = f"{raw_category.lower()} {final_category.lower()} {' '.join(title_words)}"
    for key, vals in CATEGORY_ALIASES.items():
        if key in searchable_text or any(len(v) > 3 and v.lower() in searchable_text for v in vals):
            extra_aliases.add(key)
            extra_aliases.update(v.lower() for v in vals)

    combined = (
        {raw_category.strip().lower(), final_category.lower(), "wallpaper"}
        | {a.lower() for a in primary_aliases}
        | {a.lower() for a in title_aliases}
        | set(title_words)
        | extra_aliases
    )
    return final_category, sorted(t for t in combined if t)


def main():
    extracted = extract_all_zips()
    print(f"Total images extracted from ZIPs: {extracted}")

    items = []
    idx = 1
    verified = 0
    skipped = 0

    if WALLS_DIR.exists():
        for folder in sorted(WALLS_DIR.iterdir()):
            if not folder.is_dir():
                continue

            raw_folder_name = folder.name.strip().lower()
            for file_path in sorted(folder.rglob("*")):
                if not file_path.is_file():
                    continue
                if file_path.name.lower() in IGNORE_FILENAMES or file_path.suffix.lower() not in IMAGE_EXTS:
                    continue

                if not verify_image(file_path):
                    skipped += 1
                    continue

                verified += 1
                rel_from_walls = file_path.relative_to(WALLS_DIR).as_posix()
                encoded_rel = "/".join(quote(part) for part in rel_from_walls.split("/"))

                clean_title = file_path.stem.replace("_", " ").replace("-", " ").strip().title()
                category, tags = build_tags(raw_folder_name, clean_title)

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
    
