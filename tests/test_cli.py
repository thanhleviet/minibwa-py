"""Exact-argv tests for the flag translation tables (no subprocess)."""

from __future__ import annotations

import pytest

from minibwa._cli import build_index_argv, build_map_argv

BIN = "/usr/bin/minibwa"


def _index(prefix=None, extra_args=None, **kwargs):
    full = {
        "seed": None,
        "sa_sample_rate": None,
        "low_memory": False,
        "block_size": None,
        "threads": None,
        "meth": False,
    }
    full.update(kwargs)
    return build_index_argv(BIN, "ref.fa", prefix, full, extra_args)


def _map(reads2=None, extra_args=None, **kwargs):
    full = {
        key: None
        for key in (
            "preset",
            "threads",
            "read_group",
            "base_tag",
            "short_read_len",
            "min_seed_len",
            "max_seed_occ",
            "max_gap",
            "bandwidth",
            "long_bandwidth",
            "min_chain_score",
            "sec_ratio",
            "max_secondary",
            "match_score",
            "mismatch_penalty",
            "gap_open",
            "gap_extend",
            "dp_score_cutoff",
            "rescue",
            "output_secondary",
            "batch_size",
            "output",
        )
    }
    full.update(
        {
            key: False
            for key in (
                "paf",
                "hic",
                "meth",
                "chain_only",
                "skip_pairing",
                "no_unmapped",
                "copy_comments",
                "soft_clip_supp",
                "primary_smallest_qpos",
            )
        }
    )
    full.update(kwargs)
    return build_map_argv(BIN, "idx", "reads.fq", reads2, full, extra_args)


# --- index ---------------------------------------------------------------


def test_index_defaults_omits_everything():
    assert _index() == [BIN, "index", "ref.fa"]


def test_index_prefix_positional_appended():
    assert _index(prefix="myidx") == [BIN, "index", "ref.fa", "myidx"]


def test_index_threads_seed_lowmem_meth_block():
    argv = _index(prefix="p", seed=7, threads=4, low_memory=True, block_size="10m", meth=True)
    assert argv[0:2] == [BIN, "index"]
    assert "-s" in argv and argv[argv.index("-s") + 1] == "7"
    assert "-t" in argv and argv[argv.index("-t") + 1] == "4"
    assert "-l" in argv
    assert "-b" in argv and argv[argv.index("-b") + 1] == "10m"
    assert "--meth" in argv
    assert argv[-1] == "p"


def test_index_extra_args_appended_verbatim():
    argv = _index(prefix="p", extra_args=["--future", "x"])
    assert argv[-2:] == ["--future", "x"]


# --- map -----------------------------------------------------------------


def test_map_minimal():
    assert _map() == [BIN, "map", "idx", "reads.fq"]


def test_map_preset_and_threads():
    argv = _map(preset="sr", threads=8)
    assert "-x" in argv and argv[argv.index("-x") + 1] == "sr"
    assert "-t" in argv and argv[argv.index("-t") + 1] == "8"


def test_map_paf_flag():
    assert "-f" in _map(paf=True)
    assert "-f" not in _map(paf=False)


def test_map_paired_end_second_fastq_trailing_positional():
    argv = _map(reads2="R2.fq")
    assert argv[-2:] == ["reads.fq", "R2.fq"]


def test_map_gap_open_tuple_renders_comma_pair():
    argv = _map(gap_open=(12, 23))
    assert argv[argv.index("-O") : argv.index("-O") + 2] == ["-O", "12,23"]


def test_map_gap_open_int_renders_single():
    argv = _map(gap_open=6)
    assert argv[argv.index("-O") : argv.index("-O") + 2] == ["-O", "6"]


def test_map_gap_extend_tuple():
    argv = _map(gap_extend=(2, 1))
    assert argv[argv.index("-E") : argv.index("-E") + 2] == ["-E", "2,1"]


def test_map_read_group_single_element():
    rg = "@RG\tID:foo\tSM:bar"
    argv = _map(read_group=rg)
    assert argv[argv.index("-R") + 1] == rg


def test_map_base_tag():
    argv = _map(base_tag="cs")
    assert argv[argv.index("-b") + 1] == "cs"


def test_map_rescue_equals_form():
    assert "--rescue=10" in _map(rescue=10)


def test_map_output_secondary_outn_equals_form():
    assert "--outn=3" in _map(output_secondary=3)


def test_map_boolean_bare_flags():
    argv = _map(
        no_unmapped=True,
        chain_only=True,
        soft_clip_supp=True,
        primary_smallest_qpos=True,
        hic=True,
        skip_pairing=True,
        meth=True,
        copy_comments=True,
    )
    for flag in ("-u", "--chain-only", "-Y", "-5", "--hic", "-P", "--meth", "-y"):
        assert flag in argv


@pytest.mark.parametrize(
    "kwarg,flag,value",
    [
        ("min_seed_len", "-k", 19),
        ("bandwidth", "-w", 100),
        ("long_bandwidth", "-W", 50),
        ("min_chain_score", "-m", 40),
        ("max_secondary", "-N", 5),
    ],
)
def test_map_value_flags_render_flag_then_value(kwarg, flag, value):
    # Guards the whole "value" flag class: each renders [flag, str(value)] with
    # the correct literal flag token (catches a typo or kind change in MAP_SPEC).
    argv = _map(**{kwarg: value})
    assert flag in argv
    assert argv[argv.index(flag) + 1] == str(value)


def test_map_size_strings_passed_through():
    argv = _map(batch_size="100m,1g", max_seed_occ="250", max_gap="100")
    assert argv[argv.index("-K") + 1] == "100m,1g"
    assert argv[argv.index("-c") + 1] == "250"
    assert argv[argv.index("-g") + 1] == "100"


def test_map_output_renders_dash_o():
    argv = _map(output="out.sam")
    assert argv[argv.index("-o") + 1] == "out.sam"


def test_map_extra_args_appended_verbatim():
    argv = _map(extra_args=["--xx", "1"])
    assert argv[-2:] == ["--xx", "1"]


def test_map_index_reduced_to_prefix_string():
    # build_map_argv uses os.fspath on the index; a plain string passes through.
    argv = _map()
    assert "idx" in argv


def test_map_sec_ratio_float_and_scores():
    argv = _map(sec_ratio=0.5, match_score=2, mismatch_penalty=8, dp_score_cutoff=30)
    assert argv[argv.index("-p") + 1] == "0.5"
    assert argv[argv.index("-A") + 1] == "2"
    assert argv[argv.index("-B") + 1] == "8"
    assert argv[argv.index("-s") + 1] == "30"


def test_no_shell_metacharacters_joined():
    # The argv must remain a list of discrete tokens; nothing is shell-joined.
    argv = _map(read_group="@RG\tID:foo", preset="sr")
    assert isinstance(argv, list)
    assert all(isinstance(token, str) for token in argv)
    # The read group with a tab stays one element, never split or quoted.
    assert "@RG\tID:foo" in argv
