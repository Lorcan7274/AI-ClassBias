/**
 * Builds the street-check Google Form and its responses sheet.
 *
 * 1. Go to https://script.google.com, New project, paste this file over the
 *    editor's contents, and save.
 * 2. Pick buildForm in the toolbar's function menu, press Run, and allow the
 *    permissions it asks for (Forms, Sheets).
 * 3. Open the execution log (View > Logs, or the panel at the bottom): it
 *    prints the link to fill in, the link to edit, and the responses sheet.
 *
 * Optional: put each interviewer's initials and location in INTERVIEWERS,
 * run prefilledLinks, and send each person their own link. Those two fields
 * then come pre-filled, so on the day it is three taps per answer.
 */

var INTERVIEWERS = [
  // ['LP', 'campus library entrance'],
  // ['AB', "King's Cross concourse"],
];

var CARD_COUNT = 30;

function buildForm() {
  var form = FormApp.create('CV street check');
  form.setDescription('One CV, two questions. The interviewer fills this in.')
      .setCollectEmail(false)
      .setLimitOneResponsePerUser(false)
      .setShowLinkToRespondAgain(true)
      .setConfirmationMessage('Saved. Next person.')
      .setProgressBar(false);

  form.addTextItem().setTitle('Interviewer').setHelpText('Your initials').setRequired(true);
  form.addTextItem().setTitle('Location').setHelpText('Where you are, e.g. "campus library entrance"')
      .setRequired(true);

  var cards = [];
  for (var i = 1; i <= CARD_COUNT; i++) cards.push((i < 10 ? '0' : '') + i);
  form.addListItem().setTitle('Card').setHelpText('The number in the corner').setChoiceValues(cards)
      .setRequired(true);

  form.addMultipleChoiceItem().setTitle('Would you give this person an interview?')
      .setChoiceValues(['Yes', 'No']).setRequired(true);
  form.addMultipleChoiceItem().setTitle('Private school or state school?')
      .setChoiceValues(['Private', 'State', "Don't know"]).setRequired(true);

  var likelihood = form.addTextItem()
      .setTitle('How likely are they to be invited, 0 to 100? (optional)')
      .setRequired(false);
  likelihood.setValidation(FormApp.createTextValidation()
      .setHelpText('A whole number from 0 to 100')
      .requireNumberBetween(0, 100).build());

  var sheet = SpreadsheetApp.create('CV street check (responses)');
  form.setDestination(FormApp.DestinationType.SPREADSHEET, sheet.getId());
  PropertiesService.getScriptProperties().setProperty('FORM_ID', form.getId());

  Logger.log('Fill in (send to interviewers): ' + form.getPublishedUrl());
  Logger.log('Edit the form:                  ' + form.getEditUrl());
  Logger.log('Responses sheet:                ' + sheet.getUrl());
  Logger.log('If interviewers use personal Google accounts and yours is a university one, untick '
           + '"Restrict to users in your organisation" under the form\'s Settings > Responses.');
}

function prefilledLinks() {
  var id = PropertiesService.getScriptProperties().getProperty('FORM_ID');
  if (!id) throw new Error('Run buildForm first.');
  var form = FormApp.openById(id);
  var items = form.getItems(FormApp.ItemType.TEXT);
  var interviewer = items[0].asTextItem();
  var location = items[1].asTextItem();
  if (!INTERVIEWERS.length) throw new Error('Add [initials, location] pairs to INTERVIEWERS first.');
  INTERVIEWERS.forEach(function (pair) {
    var url = form.createResponse()
        .withItemResponse(interviewer.createResponse(pair[0]))
        .withItemResponse(location.createResponse(pair[1]))
        .toPrefilledUrl();
    Logger.log(pair[0] + ' (' + pair[1] + '): ' + url);
  });
}
