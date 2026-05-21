from utils.retry import NonRetryableError, retry_call


def test_retry_call_retries_selected_exception_then_succeeds():
    calls = []

    def flaky():
        calls.append("call")
        if len(calls) < 3:
            raise TimeoutError("temporary")
        return "ok"

    result = retry_call(
        flaky,
        attempts=3,
        delays=(0.0,),
        retry_on=(TimeoutError,),
        sleep_fn=lambda _delay: None,
    )

    assert result == "ok"
    assert len(calls) == 3


def test_retry_call_does_not_retry_non_retryable_error():
    calls = []

    def permanent():
        calls.append("call")
        raise NonRetryableError("bad request")

    try:
        retry_call(
            permanent,
            attempts=3,
            delays=(0.0,),
            retry_on=(Exception,),
            sleep_fn=lambda _delay: None,
        )
    except NonRetryableError:
        pass

    assert len(calls) == 1
