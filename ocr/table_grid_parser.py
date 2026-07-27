from typing import List, Dict, Any, Tuple

def get_bbox(b: Any) -> Dict[str, int]:
    if hasattr(b, 'bounding_box') and b.bounding_box is not None:
        return b.bounding_box
    if isinstance(b, dict):
        if 'bounding_box' in b:
            return b['bounding_box']
        if 'bbox' in b:
            return b['bbox']
    return None

def get_text(b: Any) -> str:
    if hasattr(b, 'text'):
        return b.text
    if isinstance(b, dict):
        return b.get('text', '')
    return ''

def reconstruct_grid(text_blocks: List[Any], x_tol: int = 20, y_tol: int = 12) -> List[List[str]]:
    """
    Reconstructs an explicit 2D grid matrix (Rows x Columns) from OCR text blocks with bounding boxes.
    Prevents wide multi-column table text from flattening into 1D strings.
    """
    valid_blocks = []
    for b in text_blocks:
        bbox = get_bbox(b)
        if bbox and all(k in bbox for k in ('x1', 'y1', 'x2', 'y2')):
            valid_blocks.append(b)
            
    if not valid_blocks:
        return []

    # Sort blocks vertically by y1, then horizontally by x1
    sorted_blocks = sorted(valid_blocks, key=lambda b: (get_bbox(b)['y1'], get_bbox(b)['x1']))

    # 1. Cluster blocks into horizontal row bands
    rows_raw = []
    for b in sorted_blocks:
        placed = False
        bbox = get_bbox(b)
        for row in rows_raw:
            avg_y = sum(get_bbox(item)['y1'] for item in row) / len(row)
            if abs(bbox['y1'] - avg_y) <= y_tol:
                row.append(b)
                placed = True
                break
        if not placed:
            rows_raw.append([b])

    # 2. Determine unique column centroid boundaries across the page
    all_x1s = sorted([get_bbox(b)['x1'] for b in sorted_blocks])
    col_clusters = []
    for x in all_x1s:
        if not col_clusters or abs(x - sum(col_clusters[-1])/len(col_clusters[-1])) > x_tol:
            col_clusters.append([x])
        else:
            col_clusters[-1].append(x)

    col_centroids = [int(sum(c)/len(c)) for c in col_clusters]
    num_cols = len(col_centroids)

    # 3. Align row text into 2D grid cells
    grid = []
    for row in rows_raw:
        grid_row = [""] * num_cols
        for block in row:
            bbox = get_bbox(block)
            bx = bbox['x1']
            col_idx = min(range(num_cols), key=lambda idx: abs(bx - col_centroids[idx]))
            text = get_text(block)
            grid_row[col_idx] = (grid_row[col_idx] + " " + text).strip()
        grid.append(grid_row)

    return grid

def build_table_structure(text_blocks: List[Any], x_tol: int = 20, y_tol: int = 12) -> Dict[str, Any]:
    """
    Builds the table_structure dictionary format expected by LayoutRegion.
    """
    valid_blocks = []
    for b in text_blocks:
        bbox = get_bbox(b)
        if bbox and all(k in bbox for k in ('x1', 'y1', 'x2', 'y2')):
            valid_blocks.append(b)
            
    if not valid_blocks:
        return {"rows": 0, "cols": 0, "cells": []}

    sorted_blocks = sorted(valid_blocks, key=lambda b: (get_bbox(b)['y1'], get_bbox(b)['x1']))

    rows_raw = []
    for b in sorted_blocks:
        placed = False
        bbox = get_bbox(b)
        for row in rows_raw:
            avg_y = sum(get_bbox(item)['y1'] for item in row) / len(row)
            if abs(bbox['y1'] - avg_y) <= y_tol:
                row.append(b)
                placed = True
                break
        if not placed:
            rows_raw.append([b])

    all_x1s = sorted([get_bbox(b)['x1'] for b in sorted_blocks])
    col_clusters = []
    for x in all_x1s:
        if not col_clusters or abs(x - sum(col_clusters[-1])/len(col_clusters[-1])) > x_tol:
            col_clusters.append([x])
        else:
            col_clusters[-1].append(x)

    col_centroids = [int(sum(c)/len(c)) for c in col_clusters]
    num_cols = len(col_centroids)

    cells_list = []
    for r_idx, row in enumerate(rows_raw):
        for block in row:
            bbox = get_bbox(block)
            bx = bbox['x1']
            c_idx = min(range(num_cols), key=lambda idx: abs(bx - col_centroids[idx]))
            cells_list.append({
                "row": r_idx,
                "col": c_idx,
                "text": get_text(block),
                "bounding_box": bbox
            })
            
    return {
        "rows": len(rows_raw),
        "cols": num_cols,
        "cells": cells_list
    }
