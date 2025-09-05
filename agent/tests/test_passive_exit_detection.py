import types

from discharge.agents import DischargeAgent


def make_partial_agent():
    # Create instance without running __init__ (avoids Redis/API setup)
    agent = object.__new__(DischargeAgent)
    # Provide minimal session userdata used by exit detection
    agent.session = types.SimpleNamespace(userdata=types.SimpleNamespace(collected_instructions=[]))
    return agent


def test_direct_address_detection_strict():
    agent = make_partial_agent()
    f = agent._is_maya_directly_addressed

    # Direct address (should be True)
    assert f("maya, did you get that?") is True
    assert f("hey maya are you there") is True
    assert f("did you get that, maya?") is True

    # Contextual mentions (should be False)
    assert f("maybe we should ask maya about this") is False
    assert f("maya is our discharge coordinator") is False
    assert f("i think maya mentioned it earlier") is False


def test_exit_detection_phrases_and_exclusions():
    agent = make_partial_agent()
    g = agent._should_exit_passive_mode

    # Completion signals
    assert g("that's all for today") is True
    assert g("we're done here") is True
    assert g("any questions before we wrap up") is True

    # Exclusions (partial completion)
    assert g("we're almost finished with this particular instruction") is False
    assert g("i'm done with this particular example") is False

    # Social closings - only if instructions were captured
    agent.session.userdata.collected_instructions = [{"text": "foo"}]
    assert g("okay, take care and have a good day") is True

    # No instructions captured -> should not exit on social closing
    agent.session.userdata.collected_instructions = []
    assert g("okay, take care and have a good day") is False 