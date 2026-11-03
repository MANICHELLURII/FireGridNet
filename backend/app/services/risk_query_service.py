def latest_rows_by_cell(sb, table_name: str, columns: str, timestamp_column: str, cell_ids: set[str]):
    """Return newest-first rows keyed by known grid cell, using paged reads."""
    if not cell_ids:
        return {}

    latest = {}
    offset = 0
    page_size = 1000
    while True:
        page = (
            sb.table(table_name)
            .select(columns)
            .not_.is_("cell_id", "null")
            .order(timestamp_column, desc=True)
            .range(offset, offset + page_size - 1)
            .execute()
            .data
        )
        for row in page:
            if row["cell_id"] in cell_ids:
                latest.setdefault(row["cell_id"], row)
        if len(latest) >= len(cell_ids) or len(page) < page_size:
            break
        offset += page_size
    return latest


def get_grid_cell_ids(sb) -> set[str]:
    return {row["cell_id"] for row in sb.table("grid_cells").select("cell_id").execute().data}
