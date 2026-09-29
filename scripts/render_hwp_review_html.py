"""Create display-only HWP HTML without OCR, VLM, PDF or judgment execution."""
from pathlib import Path
import argparse
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--parser-root', type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.parser_root.resolve()))
    from nh_parser_fin.ingest.hwp_html import render_hwp_review_surface
    surface = render_hwp_review_surface(args.source, args.output)
    print(Path(surface['html_path']).name)


if __name__ == '__main__':
    main()
