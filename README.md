# smr_scheduler
This is the repository for the code to generate the monthly schedule for the Student Medical Response Team at the University of Calgary.
## How it Works

### Overview
Every month on the 26th at 12:00am MST, the program will download the response data from the google sheet
```
SMR Schedule Form (Responses)
```
from the corresponding form.

Based on this availability, it generates an excel sheet for the next month based on everyone's availability. It aims to be as "fair" as possible, meaning that it aims for everyone to have roughly the same amount of shifts.

Of course, a perfectly "fair" schedule might not be possible given that certain time slots might be more/less filled and senior availability might also fluctuate.

Because of this, I have included statistics. Inside the excel sheet there is a "Person Schedule" tab that contains the number of shifts everyone is working per month. In addition, there is also a "Log" tab that includes both a table version of the schedule, and more importantly, a Warnings section. The Warnings section will indicate time slots where there are less than 3 people and time slots where a senior is not available.

### How it gets the Form data
First, the excel sheet for the form is being read in by the program. If you take a look at the excel sheet, the question in the form becomes the column name. First, after getting the excel sheet, the program will fetch the column titles and search for key words. For example, if the column title is `first name (extra context):` the script would turn the column title into `firstnameextracontext` and then search for the words `first` and `name`, if the title contains it then it will match the column title. This means you can change the form questions as long as you keep the key words. Just don't include other column titles key words (don't write `last name` in the first name form question).

### How the form uses the data
First, what submissions does the program take in? Because their are only 2 terms SMR runs, the submissions it will take is based on the term. For the fall term it will only consider submissions between August 1st and November 30st. For the Winter term it will only take in submissions from December 1st and March 31st the next year. This just helps ensure only active members are considered.

### Scheduling Algorithm
The program tries to be as fair as possible, as I described in the overview. Their is also an issue of tiebreakers, if multiple people are vying for a time spot and they both have the same number of shifts that week, then how do you tie break? I've decided to do it both randomly and deterministically. Basically, instead of using something unfair like alphabetical to tie-break, I've decided to create a hash. This means that whoever gets the time slot is random, and if you run the program again the same person will be chosen, hence the determinism.

### Calendar Integration
I've included in the output a ICS integration. You know how you can "subscribe" to your school calendar (at-least my school can) for Google/Apple Calendar? Not just copy and pasting it in, but something that will update real time if any changes are made. This is ICS integration and I included it the spreadsheet. The user just needs to click on the link in the spreadsheet and they can subscribe to it in their calendar app. This way, if any changes are made to the schedule their calendar will also be updated, without them having to do anything.

Also note that because the schedules are made late each month (for the next month), the next months calendar will be mostly empty.

## Updating Data
In order adjust someones availability, all they need to do is a submit another form with their new availabilities. The program will take the latest form submission from a particular UCID for their availabilities.

Thus, a student just needs to submit their updated availabilities before the 12:00am on the 26th of the month in order for the next months schedule to consider their new availabilities.
### Manual Updates
If something happens and the schedule needs to be remade at another time, then remaking the schedule manually is also possible. On the repository home page (the page you are probably reading this), look above and click
```
Actions > (left toolbar) 📅 Generate Monthly Schedule > (right side) Run workflow > Run Workflow (green button)
```
This will run the program manually to remake the schedule for the next month.

## Security
This repository needs to be public in order to do calendar integration, because of this I've hidden the sensitive information (mainly mine to be honest for my email integration) like the Excel Sheet link and keys to setup emailing the schedule. I've also setup a hash for the ICS calendar links to the links for each person are random and have no identifying data.

# Roadmap

A form response indicating which month onward the changes will effect when someone submits a form

Make it clear that the UCID in the form is the important part.

Allow a way to remake the schedule for the current month.
- Second action?

Allow swapping of shifts

In the calendar allow special events

Number of desired shifts per week

