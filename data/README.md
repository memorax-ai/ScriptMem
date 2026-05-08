# Data Notes

For copyright reasons, this release does not include the original script
conversation text.

## Conversation Schema Example

```json
{
	"format_example": {
    "speakers": ["Speaker A", "Speaker B"],
    "session_1_date_time": "September 22, 1994",
    "session_1": [
      {
        "type": "dialogue",
        "speaker": "Speaker A",
        "dia_id": "D1:1",
        "text": "Synthetic example utterance showing the dialogue schema."
      },
      {
        "type": "narration",
        "speaker": null,
        "dia_id": "D1:2",
        "text": "Synthetic non-dialogue scene description showing the narration schema."
      }
    ]
  }
}
```

`session_xx_date_time` can default to `"Unknown"` when no reliable timestamp is
available. For Friends, we recommend using the true calendar
date, such as `"September 22, 1994"`, because that script has an 
clear temporal progression and the date metadata is useful for preserving the
timeline.
