I need you to review all of the code in $ARGUMENTS and identify opportunities to
improve or refactor. This code is assumed complete, working and ready to be
deployed. If the user did not provide a specific package, file or files to
audit, please ask for them and stop.

We are auditing for best practices, code quality and security.

1. Clarity:  The code should be clear, short and very easy to read and follow.
   Functions should be clearly named and well documented using Go standard
   library style documentation. Functions should be easy to reason about and not
   be complex.

2. Testability: Functions should be small enough to contain basic functionality
   that is easy to test.  This generally means ensuring functions do one thing.
   It also means that we isolate code that we aren't going to test, such as
   calling third party APIs etc so that we can minimize mocking.  We can add
   comments to indicate they aren't tested since they are only third party
   calls.

3. Optimized: I think there are areas of optimization possible.  Many redundant
   calls to the database that, perhaps could either be write-through cached (see
   @firestore.go for examples) or other things.

4. Safe: Safe from both a security stand point but also good practices like nil
   pointer checks, argument validation etc.

5. Complete Implementation: There should be no TODOs or other comments
   indicating incomplete code. Identify and list any incomplete code.

Analyze all the code carefully and identify areas of improvement.  Make a list
and a plan to incrementally improve and test along the way to ensure we didn't
break anything.  If there are opportunities to write tests before starting to
ensure nothing breaks, that's probably a good thing too.