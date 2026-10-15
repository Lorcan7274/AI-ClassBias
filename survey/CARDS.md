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

Six fields per answer; nothing that identifies the person.

| field | values |
|---|---|
| interviewer | your initials |
| location | e.g. "King's Cross platform 9", "campus library entrance" |
| card | 01–30 |
| interview | yes / no |
| school | private / state / don't know |
| likelihood (optional) | 0–100, "how likely are they to be invited?" if they're happy to say |

Export the form to CSV when you're done; the key turns card numbers into the
CV, base and version for the analysis.
