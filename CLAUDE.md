persistent nots and reminders for the project
this is a forcasting app for hotels

we use 3rd party systems which intergrating with;
- newbook pms for hotel room booking system
- newbook pms is also our financial records refference, epos etc feed into it
- resos for restaurant booking system
- sambapos for epos system

this project is docker container based

notes to remmber during development;
- all api interactions with the 3rd party systems should be read only, we dont want to make any changes to the production data on them
- we have done an inital attempt for frontend which is the dashboard container, it wasnt ticking my boxes so have started a fresh frontend container with styling and stucture matching previous flash invoice app container
- we will need to clear out old code and bits from database and backend so your keeping a log of new backend code/features and anything reused from old inital system so can easily clear out redundent stuff, similar in the database
- the kitchen flash app already has allot of the features/requests we will be reusing so can be used for reference on request formatting and responce data structure
- if there is no refference data for a 3rd part api endpoint or data format we should evaluate rather than guess index/keys for the data
- compile/rebuilds/restarts of containers should be done automatically as required rather than asking permission every time.
- you dont need permission to check container logs, just check them yourself when needed
