import json
from notes.note import *
import datetime

example_predictions = [
    Prediction(task="foo", predicted_completion=PredictedCompletion(date=datetime.date.today())),
    Prediction(task="foo", predicted_completion=PredictedCompletion(datetime=datetime.datetime.now())),
    Prediction(
        task="foo",
        predicted_completion=PredictedCompletion(timedelta=datetime.timedelta(days=10))
    ),
]


def test_roundtrip():
    for pred in example_predictions:
        serialized = pred.json()
        assert isinstance(serialized, str)
        deserialized = Prediction.load(serialized)
        assert pred == deserialized