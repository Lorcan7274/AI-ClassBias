# The cards, and how to run them

`python survey/make_cards.py` builds `survey/cards/cards.pdf`: the 30 implicit-arm
CVs, one per A4 page, with only a card number in the corner. Print single-sided,
ideally on card or in plastic sleeves. `survey/cards/card_key.csv` says which CV
each card is; it stays off the table.

## On the day

Two of you per card set: one holds the card, one holds the phone with the form.
Fill in interviewer, location and the time once; then for each person, before you
approach, note the card number.

Say it the same way every time:

> "Got thirty seconds for a student project? Have a look at this CV for about
> fifteen seconds. Would you give this person a job interview, yes or no? And a
> guess: did they go to a private school or a state school?"

Don't say what the study is about until after they have answered. If they ask,
it's about how people read CVs.

Go through the cards in number order, 01 to 30, then start again. Each
interviewer starts at a different card: the first at 01, the second at 11, the
third at 21, and so on. That keeps every card, and both versions of every base,
seen about equally and by different people.

## The form

`survey/google_form.gs` builds it: paste the file into a new project at
script.google.com, run `buildForm`, allow the permissions, and the log prints the
link to fill in, the link to edit, and the responses sheet. Six fields, nothing
that identifies the person:

| field | values |
|---|---|
| Interviewer | your initials |
| Location | e.g. "King's Cross platform 9", "campus library entrance" |
| Card | 01–30 |
| Would you give this person an interview? | Yes / No |
| Private school or state school? | Private / State / Don't know |
| How likely are they to be invited, 0 to 100? (optional) | a number, if they're happy to say |

Add each interviewer's initials and location to `INTERVIEWERS` in the script and
run `prefilledLinks` to give each person a link with those two fields already
filled, so an answer is three taps.

## Afterwards

In the responses sheet, File > Download > CSV, then

```
python survey/street_responses.py <the export>.csv
```

writes `survey/street_responses.csv` (one row per answer, joined to the CV
through the key) and prints the interview rate and private-school guesses for
each version, the manipulation check, and a sign test across bases.
