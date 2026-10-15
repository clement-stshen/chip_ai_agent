---
name: identify micro architecture types of module(s) in design
description: |
    When querying about the commonly used hardware components in a design, such as FIFO, Counter, MUX, Synchronizer, RAM, Arbiter, FSM, etc,
    on a given module instance, module definition or a complete design,
    the microarchitecture analysis can be used to identify the microarchitecture type and associated key signals of module(s).
    Use the microarchitecture analysis result to answer the user's query about the microarchitecture type of module(s) in the design,
    and provide a clear explanation of the analysis steps taken to arrive at the answer.
target: [design]
examples:
    - Identify the micro architecture type of module X in my design
    - Is there any FIFO in my design?
    - What is the micro architecture type of the module instantiating module Y?
    - List all synchronizers in my design
    - Given FIFO of module/instance Z, which signals are full and empty indicators?
    - How many FIFOs are present in the current design? List them in a table with their complete hierarchy information.
---

## Guidelines
1. Running microarchitecture analysis on the given module/instance or full design.
2. The analysis of whole design will be saved to a file. You should read that file to get the analysis result.
3. Use `read_files` to tead the analysis result in the generated file to identify the microarchitecture type of the specified module(s)
   and extract the key signals, behaviors, and structural patterns associated with that type.
   - The analysis result also includes compelete information per module/instance.
     Read that file to get the complete information of the specified module/instance if needed for the analysis.
4. According to the extracted information, answer the user's query with a clear explanation of the analysis steps taken to arrive at the answer.
   If the query is about identifying microarchitecture types, provide the identified types along with their key signals and behaviors.
   If the query is about listing modules of a certain type, provide a list of those modules with their instance names and file locations if available.
5. If the query is about the instances of a certain type, then follow steps below to answer the question:
   a. Identify the module name(s) matching the type specified in the query.
   b. Search through the design hierarchy to find all instances of the identified module(s).
   c. Provide the list of identified instances to user with their instance names

## Example queries and expected analysis steps:
1. Query: List all synchronizers in my design
    - Run uarch analysis on the full design
    - Based on the analysis, identify modules that are classified as Synchronizer.
    - Provides the list of identified modules to user
2. Query: Given FIFO of module/instance Z, which signals are full and empty indicators?
    - Run uarch analysis on the specified module/instance Z
    - Based on the analysis which will identify the microarchitecture type as FIFO, extract the key signals associated with the FIFO behavior.
      a. If the given module/instance Z is identify as FIFO, provides the identified signal names that are full and empty indicators.
      b. Otherwise, inform user that the specified module/instance Z is not identified as FIFO and thus full and empty indicators cannot be determined.
3. Query: Given FIFO of module/instance Z, what is the timestamp when it first became full?
    - Run uarch analysis on the specified FIFO module/instance
    - Based on the analysis, identify the signal that indicates the full status of the FIFO.
    - Based on the identified signal name and the instance, find the full signal in the design hierarchy.
    - Use other agent or tools to trace the value change of the full signal to find the timestamp when it first became full.
    - Provide the identified timestamp to the user with a summary of the analysis steps taken to arrive at the answer.
4. Query: How many FIFOs are present in the current design? List them in a table with their complete hierarchy information.
    - Run uarch analysis on the full design
    - Based on the analysis, identify all modules that are classified as FIFO.
    - For each identified FIFO module, search through the design hierarchy to find all instances of that module.
    - Compile a list of all identified FIFO instances along with their complete hierarchy information (e.g., instance name, parent module, file location).
    - Provide the compiled list to the user in a table format, along with the total count of FIFOs identified in the design.
