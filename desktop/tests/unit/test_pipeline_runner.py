from gui import PipelineRunner


def test_log_stream_replays_each_line_once():
    runner = PipelineRunner()
    runner._publish_log("first\n")
    runner._publish_log("second\n")

    streamed = list(runner.stream_logs())

    assert streamed == ["data: first\n\n", "data: second\n\n"]
