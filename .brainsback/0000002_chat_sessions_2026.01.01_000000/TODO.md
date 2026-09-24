# Strategic Blueprint

> Focus on the **what** and **why**. The code will follow.

**Hard rule**: AI agents must not edit this file and must not draft paste-ready content for it.

## The Problem
ey so- right now the app only got one single chat evrywhre nd no way to have separate chats. task 2 wants us to add chat sessions with a sidebar just like chatgpt or gemini cause u gotta be able to switch between chats nd each chat keeps its own history. nd when u talk to the model it should make an automatic title for the session based on the first message nd reply-

## Steps
gotta make a sessions table in sqlite db with id nd title nd created time. then backend needs endpoints to create a new session, list all sessions nd get the messages for a session. then make the auto title thing that grabs the first message context nd generates a short title so it dont stay untitled. then in frontend build a sidebar on the left with a new chat button nd the list of sessions so u can click them to switch. nd add pytest tests for sessions nd titles to make sure it dont break.

## Success Looks Like
we got a sidebar on the left where u can click new chat nd switch between chats. each session got its own messages saved nd they dont mix up. after the first message the session title updates automatically to something matching the conversation. nd all pytests pass.

## Notes


---
**⚠️ HUMAN ONLY**: This file is your strategic space. AI agents must not edit it.
