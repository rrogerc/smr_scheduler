# SMR Scheduler
This code generates the term-based schedule for the Student Medical Response Team at the University of Calgary.

If you have suggestions, feel free to email me. I've tried my best to design this well, but since I'm not a club member, I might have missed some nuances.

## How it Works

### Overview
This program generates a schedule for an entire **Term** at once (4 months).

- **Fall Term:** Sept - Dec
- **Winter Term:** Jan - Apr

Leaders use the dashboard to generate the schedule before each term starts. It takes everyone's availability and creates a single Excel sheet, aiming for 2 shifts per person per week.

### Key Features

#### 1. Scheduling Logic
The system uses a mathematical algorithm (Network Flow) to create a **Master Weekly Template**. Instead of scheduling every week individually, it solves for one ideal week based on availability and applies that pattern to the whole term.

This means:
1.  **Consistency:** Your shift stays the same every week (e.g., always Tuesday 10-12).
2.  **Fairness:** It strictly enforces the 2-shift cap.
3.  **Stability:** No irregular shift distribution.

**Constraints:**
- **2 Shifts Max:** Everyone gets up to 2 shifts a week.
- **Max 2 Seniors:** A slot can have at most 2 seniors.
- **Max 5 People:** Total capacity per slot is 5.
- **Multiple Shifts:** You can work multiple shifts in a day, but never two in the same time slot.

#### 2. Excel Output
The generated Excel sheet includes:
- **Visual Pattern:** The grid uses an alternating color pattern to make rows easier to follow.
- **Shift Count:** A tab showing total shifts and a monthly breakdown for each person.
- **Senior Highlighting:** Seniors are highlighted in blue.
- **Warnings:** A list of any scheduling issues (e.g., if someone couldn't get 2 shifts).

#### 3. Dashboard
- **Smart Selection:** Automatically picks the relevant term based on today's date.
- **Versioning:** Generating a new schedule creates a new version with a timestamp; it doesn't delete old ones.

### Data & Submissions
Availability is assumed to be constant for the term. The program filters form submissions by date to ensure only current responses are used:

- **Fall Term:** Submissions from Aug 1 - Nov 30.
- **Winter Term:** Submissions from Dec 1 - Mar 31.

If a student submits multiple times, only their latest submission (by UCID) is used.

### Calendar Integration
The "Shift Count" tab in the Excel sheet has a link for each person to subscribe to their personal calendar feed (ICS). This feed updates automatically if the schedule changes.

## Using the Dashboard
1. Log in with your password.
2. Select the Term and Year.
3. Click **Generate New Version**.
4. Wait about 3-4 minutes for the backend to finish, then refresh the list to see the new file.
