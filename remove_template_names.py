import os

ROOT = os.path.dirname(os.path.abspath(__file__))  # adjust if you want a different root

def process_pages_file(path: str):
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    changed = False
    new_lines = []
    for line in lines:
        if "template_name" in line and "=" in line:
            # skip this line
            changed = True
            continue
        new_lines.append(line)

    if changed:
        print(f"Cleaning template_name in: {path}")
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)


def main():
    for dirpath, dirnames, filenames in os.walk(ROOT):
        for filename in filenames:
            if filename == "pages.py":
                full_path = os.path.join(dirpath, filename)
                process_pages_file(full_path)


if __name__ == "__main__":
    main()