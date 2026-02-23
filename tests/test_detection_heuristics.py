"""Tests for wrong-number and voicemail detection heuristics."""
import pytest
from app.services.transfer_service import (
    looks_like_wrong_number_signal,
    looks_like_voicemail_signal,
)
from app.services.carrier_failure_service import looks_like_disconnected_or_invalid


class TestLooksLikeWrongNumberSignal:
    """Test wrong-number detection in patient utterances."""

    def test_wrong_number_explicit(self):
        assert looks_like_wrong_number_signal("You have the wrong number") is True

    def test_wrong_person(self):
        assert looks_like_wrong_number_signal("Wrong person, sorry") is True

    def test_not_me(self):
        assert looks_like_wrong_number_signal("That's not me") is True

    def test_this_isnt_someone(self):
        assert looks_like_wrong_number_signal("This isn't John") is True

    def test_this_is_not_someone(self):
        assert looks_like_wrong_number_signal("This is not Maria") is True

    def test_you_have_the_wrong(self):
        assert looks_like_wrong_number_signal("you have the wrong person") is True

    def test_no_one_by_that_name(self):
        assert looks_like_wrong_number_signal("There's no one by that name here") is True

    def test_dont_know_who(self):
        assert looks_like_wrong_number_signal("I don't know who that is") is True

    def test_normal_greeting(self):
        assert looks_like_wrong_number_signal("Hello, how can I help you?") is False

    def test_empty(self):
        assert looks_like_wrong_number_signal("") is False

    def test_none(self):
        assert looks_like_wrong_number_signal(None) is False

    def test_case_insensitive(self):
        assert looks_like_wrong_number_signal("WRONG NUMBER") is True


class TestLooksLikeVoicemailSignal:
    """Test voicemail detection from transcript text."""

    def test_leave_a_message(self):
        assert looks_like_voicemail_signal("Please leave a message after the beep") is True

    def test_at_the_tone(self):
        assert looks_like_voicemail_signal("Please record your message at the tone") is True

    def test_after_the_beep(self):
        assert looks_like_voicemail_signal("Leave your message after the beep") is True

    def test_cannot_take_call(self):
        assert looks_like_voicemail_signal("I cannot take your call right now") is True

    def test_not_available(self):
        assert looks_like_voicemail_signal("I'm not available right now") is True

    def test_im_not_available(self):
        assert looks_like_voicemail_signal("im not available, leave a message") is True

    def test_leave_your_name(self):
        assert looks_like_voicemail_signal("Please leave your name and number") is True

    def test_leave_your_number_and_name(self):
        assert looks_like_voicemail_signal("Leave your number and name") is True

    def test_voicemail_word(self):
        assert looks_like_voicemail_signal("You have reached the voicemail of...") is True

    def test_voice_mail_two_words(self):
        assert looks_like_voicemail_signal("This is the voice mail box for...") is True

    def test_normal_conversation(self):
        assert looks_like_voicemail_signal("Hello, yes this is Jane speaking") is False

    def test_empty(self):
        assert looks_like_voicemail_signal("") is False

    def test_none(self):
        assert looks_like_voicemail_signal(None) is False


class TestLooksLikeDisconnectedOrInvalid:
    """Test disconnected/invalid number keyword detection."""

    def test_disconnected(self):
        assert looks_like_disconnected_or_invalid("number disconnected") is True

    def test_not_in_service(self):
        assert looks_like_disconnected_or_invalid("the number is not in service") is True

    def test_does_not_exist(self):
        assert looks_like_disconnected_or_invalid("this number does not exist") is True

    def test_failed_to_route(self):
        assert looks_like_disconnected_or_invalid("failed to route call") is True

    def test_normal_completion(self):
        assert looks_like_disconnected_or_invalid("call completed") is False
