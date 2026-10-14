"""Đọc / ghi đầu ra của module features (data/features/)."""
import pandas as pd

from common.config import FEATURES_DB
from common.db import connect


def write_table(df: pd.DataFrame, name: str) -> None:
    conn = connect(FEATURES_DB)
    df.to_sql(name, conn, if_exists="replace", index=False)
    conn.close()


def read_table(name: str) -> pd.DataFrame:
    conn = connect(FEATURES_DB)
    df = pd.read_sql(f"SELECT * FROM {name}", conn)
    conn.close()
    return df
