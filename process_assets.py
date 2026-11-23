import json
import zipfile
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import quote
from PIL import Image
from catalog_aliases import CATEGORY_ALIASES

BASE_URL = "https://wallpaper-assets-5l7.pages.dev"
WALLPAPERS_ROOT = Path("wallpapers")
IMAGES_ROOT = Path("images")
OUT_JSON = Path("wallpapers.json")

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
DUMMY_NAMES = {"fake.file", "fake.imsge", ".gitkeep", ".ds_store", "thumbs.db"}
SIMILARITY_THRESHOLD = 0.65


def similarity(a: str, b: str) -> float:
    x = a.strip().lower()
    y = b.strip().lower()
    if not x or not y:
        return 0.0
    if x == y:
        return 1.0
    if len(x) >= 4 and len(y) >= 4 and (x in y or y in x):
        return 0.85
    return SequenceMatcher(None, x, y).ratio()


def match_category(raw_name: str) -> tuple[str, list[str]]:
    cleaned = raw_name.replace("_", " ").replace("-", " ").strip().lower()
    if cleaned in CATEGORY_ALIASES:
        return cleaned, CATEGORY_ALIASES[cleaned]

    best_key = cleaned
    best_score = 0.0
    tokens = [t for t in cleaned.split() if len(t) >= 3] + [cleaned]

    for key, aliases in CATEGORY_ALIASES.items():
        candidates = [key] + [a.lower() for a in aliases]
        for tok in tokens:
            for cand in candidates:
                score = similarity(tok, cand)
                if score > best_score:
                    best_score = score
                    best_key = key

    if best_score >= SIMILARITY_THRESHOLD:
        return best_key, CATEGORY_ALIASES.get(best_key, [])

    return cleaned.replace(" ", "_") or "general", []


def verify_image(file_path: Path) -> bool:
    if file_path.name.lower() in DUMMY_NAMES:
        return False
    if not file_path.is_file() or file_path.stat().st_size <= 0:
        print(f"[SKIP EMPTY/INVALID] {file_path}")
        return False
    if file_path.suffix.lower() not in IMAGE_EXTS:
        return False
    try:
        with Image.open(file_path) as im:
            im.verify()
        with Image.open(file_path) as im:
            w, h = im.size
            if w <= 0 or h <= 0:
                print(f"[SKIP ZERO SIZE] {file_path}")
                return False
        return True
    except Exception as exc:
        print(f"[SKIP CORRUPT] {file_path} -> {exc}")
        return False


def extract_zips_in_wallpapers() -> int:
    extracted = 0
    if not WALLPAPERS_ROOT.exists():
        return 0

    for folder in sorted(WALLPAPERS_ROOT.iterdir()):
        if not folder.is_dir():
            continue
        folder_cat, _ = match_category(folder.name)

        for zp in sorted(folder.rglob("*.zip")):
            if not zp.is_file():
                continue
            try:
                with zipfile.ZipFile(zp, "r") as zf:
                    for member in zf.infolist():
                        if member.is_dir():
                            continue
                        rel = Path(member.filename)
                        if rel.is_absolute() or ".." in rel.parts:
                            continue
                        if any(p.startswith("__MACOSX") or p.lower() in DUMMY_NAMES for p in rel.parts):
                            continue

                        fname = rel.name
                        ext = Path(fname).suffix.lower()
                        if ext not in IMAGE_EXTS:
                            continue

                        target_dir = WALLPAPERS_ROOT / folder_cat
                        target_dir.mkdir(parents=True, exist_ok=True)
                        dest = target_dir / fname
                        if dest.exists():
                            stem = Path(fname).stem
                            idx = 1
                            while (target_dir / f"{stem}_{idx}{ext}").exists():
                                idx += 1
                            dest = target_dir / f"{stem}_{idx}{ext}"

                        with zf.open(member) as src, open(dest, "wb") as dst:
                            dst.write(src.read())
                        extracted += 1

                zp.unlink(missing_ok=True)
                print(f"[ZIP EXTRACTED & REMOVED] {zp}")
            except zipfile.BadZipFile:
                print(f"[BAD ZIP SKIPPED] {zp}")

    return extracted


def build_tags(raw_cat: str, title: str, file_stem: str) -> tuple[str, list[str]]:
    cat_key, cat_aliases = match_category(raw_cat)
    title_key, title_aliases = match_category(f"{title} {file_stem}")
    final_cat = cat_key if cat_key != "general" else title_key

    words = [
        w.strip().lower()
        for w in f"{raw_cat} {final_cat} {title} {file_stem}".replace("_", " ").replace("-", " ").split()
        if len(w.strip()) > 1
    ]

    tags = (
        {final_cat.lower(), raw_cat.lower(), "wallpaper"}
        | {a.lower() for a in cat_aliases}
        | {a.lower() for a in title_aliases}
        | set(words)
    )
    return final_cat, sorted(t for t in tags if t)


def collect_from_root(root_dir: Path, source_label: str, start_idx: int, skipped_ref: list[int]) -> list[dict]:
    items = []
    idx = start_idx
    if not root_dir.exists():
        return items

    for folder in sorted(root_dir.iterdir()):
        if not folder.is_dir():
            continue
        raw_folder = folder.name.strip().lower()

        for file_path in sorted(folder.rglob("*")):
            if not file_path.is_file() or file_path.name.lower() in DUMMY_NAMES:
                continue
            if file_path.suffix.lower() not in IMAGE_EXTS:
                continue
            if not verify_image(file_path):
                skipped_ref[0] += 1
                continue

            clean_title = file_path.stem.replace("_", " ").replace("-", " ").strip().title()
            category, tags = build_tags(raw_folder, clean_title, file_path.stem)
            rel_posix = file_path.relative_to(Path(".")).as_posix()
            encoded_path = "/".join(quote(p) for p in rel_posix.split("/"))

            items.append({
                "id": str(idx),
                "title": clean_title,
                "category": category,
                "source": source_label,
                "tags": tags,
                "url": f"{BASE_URL}/{encoded_path}"
            })
            idx += 1

    return items


def main():
    zip_extracted = extract_zips_in_wallpapers()
    print(f"Extracted images from ZIPs: {zip_extracted}")

    skipped = [0]
    wp_items = collect_from_root(WALLPAPERS_ROOT, "zip_wallpaper", 1, skipped)
    img_items = collect_from_root(IMAGES_ROOT, "direct_image", len(wp_items) + 1, skipped)
    all_items = wp_items + img_items

    OUT_JSON.write_text(json.dumps(all_items, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"ZIP items: {len(wp_items)} | Direct image items: {len(img_items)} | Skipped: {skipped[0]} | Total: {len(all_items)}")


if __name__ == "__main__":
    main()
                               
