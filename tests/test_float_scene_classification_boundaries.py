from float_scene_test_utils import build_binary_frame, classify_frame


def test_bright_frontier_is_monotonic_across_bright_ratio_and_base_level():
    bright_counts = [15, 18, 20, 22, 25, 28, 30, 35]
    base_levels = [160, 168, 176, 184, 192]

    for base_level in base_levels:
        bright_hits = [
            classify_frame(build_binary_frame(base_level, 224, bright_count, total=100)).raw_scene_name == "Bright"
            for bright_count in bright_counts
        ]
        assert bright_hits == sorted(bright_hits)

    for bright_count in bright_counts:
        bright_hits = [
            classify_frame(build_binary_frame(base_level, 224, bright_count, total=100)).raw_scene_name == "Bright"
            for base_level in base_levels
        ]
        assert bright_hits == sorted(bright_hits)


def test_dark_split_moves_monotonically_from_dark_ii_toward_dark_i_when_mid_gray_detail_increases():
    detail_counts = [0, 5, 10, 15, 20, 25, 30]
    dark_ii_hits = [
        classify_frame(build_binary_frame(0, 64, detail_count, total=100)).raw_scene_name == "Dark II"
        for detail_count in detail_counts
    ]

    assert dark_ii_hits == sorted(dark_ii_hits, reverse=True)
    assert classify_frame(build_binary_frame(0, 64, 0, total=100)).raw_scene_name == "Dark II"
    assert classify_frame(build_binary_frame(0, 64, 20, total=100)).raw_scene_name == "Dark I"


def test_revised_boundary_examples_match_expected_scenes():
    assert classify_frame(build_binary_frame(170, 224, 20, total=100)).scene_name == "Normal"
    assert classify_frame(build_binary_frame(176, 224, 25, total=100)).scene_name == "Bright"
    assert classify_frame(build_binary_frame(0, 64, 20, total=100)).scene_name == "Dark I"
