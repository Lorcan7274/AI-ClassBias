# The human check: one form, one CV each

Friends get one link. The form asks the day of the month they were born on,
which quietly picks one of the 30 implicit-arm CVs, shows the job in three
lines and that CV as an image, and asks four questions: invite to interview
(yes/no), how likely 0–10, private or state school, and what they think the
parents do. Two minutes, anonymous, nothing identifying.

## Building the form

`survey/google_form.gs`: paste it into a new project at script.google.com, run
`buildForm`, allow the permissions, and the log prints the link to send, the link
to edit, and the responses sheet. The images come from this repository on
GitHub (`survey/cards/web/`), so the branch must be pushed before the script runs.
If your Google account is a university one and friends use personal accounts,
untick "Restrict to users in your organisation" under Settings > Responses.

## What to aim for

Each CV is seen by everyone born on one day of the month (day 31 shares with
day 1), so 100 responses gives roughly three per card and six or seven per base.
That is enough for the manipulation check, which should be lopsided if the
markers work, and for a rough human interview rate per version. It is not enough
to see effects of a few points, so the write-up should call it a check on the
stimuli and a human baseline, not a parallel test.

## Afterwards

In the responses sheet, File > Download > CSV, then

```
python survey/form_responses.py <the export>.csv
```

writes `survey/form_responses.csv` (one row per response, joined to the CV
through `survey/cards/card_key.csv`) and prints the interview rate, mean
likelihood and private-school guesses for each version, the manipulation check,
and a sign test across bases.

## The cards

`python survey/make_cards.py` rebuilds everything from `cvs/`: the phone-width
images the form uses, `cards.pdf` with the same 30 CVs on numbered A4 pages in
case a printed version is ever wanted, and the key.
