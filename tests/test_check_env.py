from check_env import check_db_url, mask

POOLER = "aws-0-ap-south-1.pooler.supabase.com"


def test_mask_shows_only_first_8_and_last_4() -> None:
    assert mask("sk-or-v1-abcdefghijklmnop") == "sk-or-v1...mnop"
    assert mask("short") == "*****"
    assert mask("") == "<empty>"
    assert mask(None) == "<empty>"


def test_db_url_shape() -> None:
    assert check_db_url("") == "FAIL"
    assert (
        check_db_url(f"postgresql://postgres.x:[YOUR-PASSWORD]@{POOLER}:5432/postgres")
        == "FAIL"
    )
    assert check_db_url(f"postgresql://postgres.x:pw@{POOLER}:5432/postgres") == "PASS"
    assert check_db_url(f"postgresql://postgres.x:pw@{POOLER}:6543/postgres") == "WARN"
    assert (
        check_db_url("postgresql://postgres:pw@db.x.supabase.co:5432/postgres")
        == "WARN"
    )
