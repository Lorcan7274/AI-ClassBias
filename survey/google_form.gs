/**
 * Builds the CV-check Google Form: one link for everyone, each person sees one
 * of the 30 CVs and answers four questions.
 *
 * 1. Go to https://script.google.com, New project, paste this file over the
 *    editor's contents, save.
 * 2. Pick buildForm in the toolbar's function menu, press Run, and allow the
 *    permissions it asks for (Forms, Sheets, fetching the images).
 * 3. Open the execution log (the panel at the bottom): it prints the link to
 *    send, the link to edit the form, and the responses sheet.
 *
 * How one link shows different CVs: the first page asks for the day of the
 * month the person was born on, and each of the 31 answers jumps to one of
 * 30 sections, each holding one CV and the questions. That is a near-random
 * assignment that needs no codes and no instructions. Day 31 shares card 01.
 */

var IMAGE_BASE = 'https://raw.githubusercontent.com/Lorcan7274/AI-ClassBias/stimulus-set/survey/cards/web/';
var CARD_COUNT = 30;

var ROLE = 'Job description: An entry-level analyst job in London for a recent graduate. The work '
  + 'is building reports in Excel, cleaning up company data, and explaining what the numbers mean '
  + 'to managers. They want someone with a good college degree in any subject, skills in Excel and '
  + 'a coding language like SQL or Python, some experience working with real data, and clear '
  + 'communication. Only 3 in 10 applicants get an interview.';

function pad(n) { return (n < 10 ? '0' : '') + n; }

function buildForm() {
  var form = FormApp.create('CV check');
  form.setDescription(
      'A two-minute student research task. You will see a job and one applicant\'s CV, '
      + 'then answer four quick questions. There are no right answers; go with your first '
      + 'impression. Nothing identifying is collected and the answers are only used in aggregate.')
      .setCollectEmail(false)
      .setLimitOneResponsePerUser(false)
      .setShowLinkToRespondAgain(false)
      .setConfirmationMessage('Thanks, that\'s all.')
      .setProgressBar(false);

  var day = form.addListItem()
      .setTitle('What day of the month were you born on?')
      .setHelpText('This only picks which CV you see.')
      .setRequired(true);

  var sections = [];
  for (var c = 1; c <= CARD_COUNT; c++) {
    var pageBreak = form.addPageBreakItem().setTitle('The job and the CV');
    if (c > 1) {
      // Reaching this page break by scrolling on from the previous section means
      // that section is finished: submit rather than show the next CV.
      pageBreak.setGoToPage(FormApp.PageNavigationType.SUBMIT);
    }
    sections.push(pageBreak);

    form.addSectionHeaderItem().setTitle('The job').setHelpText(ROLE);

    var blob = UrlFetchApp.fetch(IMAGE_BASE + 'card-' + pad(c) + '.png').getBlob();
    form.addImageItem().setTitle('The applicant\'s CV').setImage(blob).setWidth(700)
        .setAlignment(FormApp.Alignment.CENTER);

    form.addMultipleChoiceItem()
        .setTitle('Would you invite this person to interview?')
        .setChoiceValues(['Yes', 'No']).setRequired(true);
    form.addScaleItem()
        .setTitle('How likely is it that this person gets an interview?')
        .setBounds(0, 10).setLabels('Very unlikely', 'Very likely').setRequired(true);
    form.addMultipleChoiceItem()
        .setTitle('What kind of school do you think they went to?')
        .setChoiceValues(['Private (fee-paying)', 'State', 'No idea']).setRequired(true);
    form.addTextItem()
        .setTitle('What do you think their parents do for a living? (optional)')
        .setRequired(false);
  }

  var choices = [];
  for (var d = 1; d <= 31; d++) {
    choices.push(day.createChoice(String(d), sections[(d - 1) % CARD_COUNT]));
  }
  day.setChoices(choices);

  var sheet = SpreadsheetApp.create('CV check (responses)');
  form.setDestination(FormApp.DestinationType.SPREADSHEET, sheet.getId());

  Logger.log('Send this link:   ' + form.getPublishedUrl());
  Logger.log('Edit the form:    ' + form.getEditUrl());
  Logger.log('Responses sheet:  ' + sheet.getUrl());
  Logger.log('If friends use personal Google accounts and yours is a university one, untick '
           + '"Restrict to users in your organisation" under the form\'s Settings > Responses.');
}

// Change the job text on an existing form without rebuilding it: put the form's
// ID (the long string in its edit link) in FORM_ID, edit ROLE above, run this.
var FORM_ID = '';

function updateRole() {
  if (!FORM_ID) throw new Error('Put the form ID in FORM_ID first.');
  var form = FormApp.openById(FORM_ID);
  var items = form.getItems(FormApp.ItemType.SECTION_HEADER);
  var n = 0;
  for (var i = 0; i < items.length; i++) {
    if (items[i].getTitle() === 'The job') {
      items[i].asSectionHeaderItem().setHelpText(ROLE);
      n++;
    }
  }
  Logger.log('Updated the job text in ' + n + ' sections.');
}
