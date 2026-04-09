# Fitted Information Tree


## What Is It?

A Fitted Information Tree (FIT) is a way to structure information in an agent and context friendly way.
It allows just the right amount of information to be accessed for any given activity or task.
It leaves pointers in context for accessing additional information as the session evolves and more information becomes relevant.

This repository contains python scripts for turning a standard large markdown file into a FIT.

## How to Use It? (Agentic Skill)

Follow this procedure when reading a document structured as a fitted information tree.

When it seems relevant to a task, read the root node file.
This relevance assessment might be based on memory, a simple prompt in AGENTS.md, a user prompt or your own intuition and initiative.
Once you've read the document, read any linked documents relevant to the task at hand. 
Read only documents relevant to the task.
Examine any token load information (optionally included in parentheses after the link) and avoid documents that are too large (>5k tokens).
If additional nodes become relevant later in a session, read them before proceeding.
Follow this procedure recursively down the tree.


## How to Generate One? (Agentic Skill)

Follow this pattern when creating and editing documents that are likely to be read by an agent and loaded completely into context.

The top level node is a reasonably sized (3k tokens or less) overview document that links to subdocuments that contain additional details.
If one of those subdocuments subsequently grows too large, it becomes an overview with links to subdocuments.

Sub-documents are located in a folder named after the original document, lowercased and without the extension (e.g. `BERNARD.md` links to `bernard/model-candidates.md`)
Links to subdocuments should use relative file paths in standard markdown link format where both the link text and target are the same. (e.g. [bernard/model-candidates.md](bernard/model-candidates.md))
Links to subdocuments should also include a parenthetical token estimate after the link for smarter agent context management (e.g. (~1760 tokens)). May be estimated at ~4 chars per token.

Documents over 3k tokens should be refactored. Documents should never exceed 5k tokens.
If the document is also a system file, also follow any other relevant guidelines for editing system files.