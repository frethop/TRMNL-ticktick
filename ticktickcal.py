import logging
import requests
import ticktickutils as tt
from datetime import datetime
from datetime import time
from datetime import timedelta
from datetime import timezone
import pytz
import os.path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

version = "0.7 (111224)"

logging.basicConfig(filename='ticktick-trml.log', encoding='utf-8', level=logging.DEBUG)
logger = logging.getLogger("TICKTICK-TRMNL")
logger.info("TickTick TRMNL started on "+str(datetime.now()))

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]

lists = tt.get_user_project()
todaysTasks = []
today = datetime.now()

rticktickDateFormat = "%Y-%m-%dT%H:%M:%S"
#ticktickDateFormat = "yyyy-MM-dd'T'HH:mm:ssZ"
ticktickDateFormat = "%Y-%m-%d"

def isToday(dateString):
    global today
    dateString = dateString[:10]
    dt = datetime.strptime(dateString, ticktickDateFormat)
    return today.date() == dt.date()

def slotnum(slot, start, end):
    if start.time() == slot.time():
        return 1
    else:
        slot = slot.replace(tzinfo=None)
        start = start.replace(tzinfo=None)
        delta = start - slot
        sl = delta.minutes % 30

creds = None
# The file token.json stores the user's access and refresh tokens, and is
# created automatically when the authorization flow completes for the first
# time.
#if os.path.exists("token.json"):
try:
    creds = Credentials.from_authorized_user_file("token.json", SCOPES)
except:
    logger.error("token.json does not exist.")
# If there are no (valid) credentials available, let the user log in.
if not creds or not creds.valid:
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        flow = InstalledAppFlow.from_client_secrets_file(
            "credentials.json", SCOPES
        )
        creds = flow.run_local_server(port=0)
# Save the credentials for the next run
with open("token.json", "w") as token:
    token.write(creds.to_json())

try:
    service = build("calendar", "v3", credentials=creds)

    # Call the Calendar API
    now = datetime.now(timezone.utc)
    #now = datetime.utcnow().isoformat() + "Z"  # 'Z' indicates UTC time
    now = now.replace(hour=0,minute=0)
    now = str(now).replace(" ","T")
    logger.info("Getting the upcoming 10 events")
    events_result = (
        service.events()
        .list(
            calendarId="primary",
            timeMin=now,
            maxResults=40,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )
    events = events_result.get("items", [])

    if not events:
      logger.info("No upcoming events found.")

except HttpError as error:
    logger.error(f"An error occurred: {error}")

## Gather all the tasks for today
for list in lists:
    try:
        tasks = tt.get_project_with_data(project_id=list['id'])['tasks']
    except:
        logger.error("Too early for TickTick")
        exit() 

    for task in tasks:
        try: 
            #print(task['title']+":"+task['startDate']+" to "+task['dueDate'])
            if isToday(task['startDate']):
                logger.debug("Ticktick entry: "+str(task))
                todaysTasks.append(task)
        except:
            pass

## Gather the events for today -- package them in a dictionary structure like that from TickTick
for ev in events:
    start = ev["start"].get("dateTime", ev["start"].get("date"))
    if isToday(start):
        task = {}
        task['startDate'] = ev["start"].get("dateTime", ev["start"].get("date"))
        task['dueDate'] = ev["end"].get("dateTime", ev["start"].get("date"))
        task['title'] = ev['summary']
        task['timeZone'] = ev['start']['timeZone']
        task['status'] = -1
        logger.debug("Calendar event: "+str(task))
        todaysTasks.append(task)

## Now start the HTML generation process.
## Initialization

tasklist = ""
html = ''

timeslot = datetime.strptime("1/1/2024, 07:00", "%m/%d/%Y, %H:%M") 
timeslot = datetime.now().replace(hour=7).replace(minute=0).replace(second=0).replace(microsecond=0)

## This is the slot loop.  "increment" represents the increment from start by 1/4 hour.  There
## are 11 increments per side.

for increment in range(0,20):

    slot = timeslot+timedelta(minutes=(increment*15))
 
    ## "side" represents the column
    for side in [0,1]:
        slot = slot+timedelta(minutes=300*side)  # compute the correct slot
         
        hourstr = slot.strftime("%-I:%M")
        logger.debug("--- "+hourstr)

        ## Generate starting HTML.  Note the "X + hourstr + X" -- number of columns fixed 
        ## up later
        html += '<div class="item">'
        if slot.minute % 30 == 0:
            html +=    '<div class="meta"><span class="index">'+hourstr+'</span></div>'
        else:
            html +=    '<div class="meta"><span class="index">'+"&nbsp;"+'</span></div>'
        html +=    '<div class="content">'
        html +=       '<div class="grid grid--cols-X' + hourstr +'X">'

        ## Check each task/event in the list against the time slot
        startLength = len(html)
        checkTasks = todaysTasks.copy()
        columns = 0
        max = 1
        for task in checkTasks:
            ## We need timezone-aware time variables
            tzone = pytz.timezone(task['timeZone'])

            ## Start of the task/event
            t = task['startDate'][:19]
            start = datetime.strptime(t, rticktickDateFormat)
            if task['status'] == -1:
                start = start.replace(second=0, tzinfo=tzone)
            else:
                start = start.replace(second=0, tzinfo=pytz.UTC)
                start = start.astimezone(tzone)
            ## round to a 15 min boundary
            originalStart = None
            if start.time().minute % 15 != 0:
                originalStart = start
                newminute = int(start.time().minute / 15) * 15
                start = start.replace(minute=newminute)

            ## End of the task/event
            e = task['dueDate'][:19]
            end = datetime.strptime(e, rticktickDateFormat)
            if task['status'] == -1:
                end = end.replace(second=0, tzinfo=tzone)
            else:
                end = end.replace(second=0, tzinfo=pytz.UTC)
                end = end.astimezone(tzone)

             ## round to a 15 min boundary
            if end.time().minute % 15 != 0:
                newminute = (int(end.time().minute / 15)+1) * 15
                if newminute > 45:
                    end = end.replace(minute=0)
                    end = end + timedelta(hours=1)
                else:
                    end = end.replace(minute=newminute)
           
            if start.time() == end.time():
                end = end + timedelta(minutes=15) 

            ## Start time for the task must be at slot time or slot time + 15 minutes
##            if (start.time() <= slot.time() or start.time() <=  (slot + timedelta(minutes=15)).time()) and end.time() > slot.time():
            if start.time() <= slot.time() and end.time() > slot.time():
                logger.debug("   Checking "+task['title'] + "...from "+str(start.time())+" to "+str(end.time())+" against "+str(slot))

#                if start.time() == slot.time() or start.time() == (slot+timedelta(minutes=15)).time():
                if start.time() == slot.time():
                    duration = start.strftime("%-I:%M")+" to "+end.strftime("%-I:%M")
                    logger.debug(">>> Start time matched: "+task['title']+". Duration = "+duration)

                    html += '<div>'
                    html +=     '<div class="b-h-gray-1" width="100%"></div>'
                    if task['status'] == -1:
                        html +=     '<span class="title title--small timeslot b-v-gray-1 bg-gray-6">'
                    else:
                        html +=     '<span class="title title--small timeslot b-v-gray-1 bg-gray-5">'
                    html +=         '<div class="clamp--1">'
                    if originalStart == None:
                        html +=             task['title']
                    else:
                        startstr = originalStart.strftime("%-I:%M")
                        html +=             task['title'] + " ({})".format(startstr)
                    html +=         '</div>'
                    html +=     '</span>'
                    html +=     '<span class="w-right b-v-gray-1" >&nbsp;</span>'

                    if start.time() == (end - timedelta(minutes=15)).time():
                        html +=     '<div class="w-full-bottom b-h-gray-1" width="100%">&nbsp;</div>'
                    html += '</div>'
                    columns += 1
                    max = columns
                else:
                    testslot = slot.replace(tzinfo=tzone)
                    ##testslot = testslot.astimezone(tzone)
                    slots = int((end - start).seconds / 60 / 15)
                    whichslot = int((end - testslot).seconds / 60 / 15)
                    if whichslot > 0:
                        s = "&nbsp;"
                        html += '<div>'
                        if task['status'] == -1:
                            html +=     '<span class="title title--small timeslot b-v-gray-1 bg-gray-6">'
                        else:
                            html +=     '<span class="title title--small timeslot b-v-gray-1 bg-gray-5">'
                        html +=         "&nbsp;"
                        html +=     '</span>'
                        html +=     '<span class="w-right b-v-gray-1">&nbsp; </span>'
                        if whichslot == 1:
                            html +=     '<div class="w-full-bottom b-h-gray-1" width="100%">&nbsp;</div>'
                        html += '</div>'
                        columns += 1
                        max = columns if columns > max else max
                    else:
                        print("SHOULD NOT BE HERE")

                if start.time() == end.time():
                    end = end + timedelta(minutes=15)    
 
                if end.time() == slot.time():
                    html +=     '<div class="w-full-bottom b-h-gray-1" width="100%"></div>'
                    todaysTasks.remove(task)

        if len(html) == startLength:
            html += '<div>'
            html +=     '<span class="title title--small timeslot">'
            html +=         "&nbsp;"
            html +=     '</span>'
            html += '</div>'
            columns = 1

        html = html.replace("X"+hourstr+"X", str(max))
        max = 1 if columns == 1 else max

        html +=        '</div>'
        html +=    '</div>'
        html += '</div>'

todaystr = datetime.now().strftime("%m/%d/%Y %-I:%M")

url = "https://usetrmnl.com/api/custom_plugins/58ddda97-f6c6-4c45-a74c-5e83866b591b"
variables = {"merge_variables": {"text": html, "date": todaystr }}
result = requests.post(url, json=variables)
if result.status_code != 200:
    logger.error(result.text)

