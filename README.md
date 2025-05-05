# smr_scheduler
This is the repository for the code to generate the monthly schedule for the Student Medical Response Team at the University of Calgary.
## How it Works
Every month on the 26th at 12:00am MST, the program will download the response data from the google sheet
```
SMR Schedule Form (Responses)
```
from the corresponding form.

Based on this availability, it generates an excel sheet for the next month based on everyones availability. It aims to be as "fair" as possible, meaning that it aims for everyone to have roughly the same amount of shifts.

Of course, a perfectly "fair" schedule might not be possible given that certain time slots might be more/less filled and senior availability might also fluctuate.

Because of this, I have included statistics. Inside the excel sheet there is a "Person Schedule" tab that contains the number of shifts everyone is working per month. In addition, there is also a "Log" tab that includes both a table version of the schedule, and more importantly, a Warnings section. The Warnings section will indicate time slots where there are less than 3 people and time slots where a senior is not available.
## Updating Data
In order adjust someones availability, all they need to do is a submit another form with their new availabilities. The program will take the latest form submission from a particular UCID for their availabilities.

Thus, a student just needs to submit their updated availabilities before the 12:00am on the 26th of the month in order for the next months schedule to consider their new availabilities.
### Manual Updates
If something happens and the schedule needs to be remade at another time, then remaking the schedule manually is also possible. On the repository home page (the page you are probably reading this), look above and click
```
Actions > (left toolbar) 📅 Generate Monthly Schedule > (right side) Run workflow > Run Workflow (green button)
```
This will run the program manually to remake the schedule for the next month.
# Roadmap
Figure out a way to remove people from the form
- Only include people from an official member spreadsheet?
- Only include submissions that in certain dates (like term)?

A form response indicating which month onward the changes will effect when someone submits a form

Simplify the spreadsheet creation
- Upload the created excel sheet on google drive instead of just creating it in the repo?
- Email it to the president?

Calendar integration, so people can subscribe on their calendar app to see only their scheduled time slots. Also allows people to check the schedule from their phone.

Make it clear that the UCID in the form is the important part.

Allow a way to remake the schedule for the current month.
- Second action?

Allow swapping of shifts


