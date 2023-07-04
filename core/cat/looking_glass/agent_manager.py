import re
from copy import copy

from langchain.agents import AgentExecutor, LLMSingleActionAgent, AgentOutputParser
from langchain.chains import LLMChain

from cat.looking_glass.prompts import ToolPromptTemplate
from cat.looking_glass.output_parser import ToolOutputParser
from cat.log import log


class AgentManager:
    """Manager of Langchain Agent.

    This class manages the Agent that uses the LLM. It takes care of formatting the prompt and filtering the tools
    before feeding them to the Agent. It also instantiates the Langchain Agent.

    Attributes
    ----------
    cat : CheshireCat
        Cheshire Cat instance.

    """
    def __init__(self, cat):
        self.cat = cat


    def execute_tool_agent(self, agent_input, allowed_tools):

        allowed_tools_names = [t.name for t in allowed_tools]

        prompt = ToolPromptTemplate(
            template="""Answer the following question: `{input}`
You can only reply using these tools:

{tools}

If no tool is useful, just reply "Final Answer: ?"
If you want to use a tool, use the following format:

Action: the name of the action to take, should be one of [{tool_names}]
Action Input: the input to the action
Observation: the result of the action
... (this Action/Action Input/Observation can repeat N times)
Final Answer: the final answer to the original input question (or "?" if no tool is adapt)

Begin!

Question: {input}
{agent_scratchpad}""",
            tools=allowed_tools,
            # This omits the `agent_scratchpad`, `tools`, and `tool_names` variables because those are generated dynamically
            # This includes the `intermediate_steps` variable because it is needed to fill the scratchpad
            input_variables=["input", "intermediate_steps"]
        )

        log("Using prompt", "INFO")
        log(prompt.template, "INFO")

        # main chain
        agent_chain = LLMChain(prompt=prompt, llm=self.cat.llm, verbose=True)

        # init agent
        agent = LLMSingleActionAgent(
            llm_chain=agent_chain,
            output_parser=ToolOutputParser(),
            stop=["\nObservation:"],
            allowed_tools=allowed_tools_names,
            verbose=True
        )

        # agent executor
        agent_executor = AgentExecutor.from_agent_and_tools(
            agent=agent,
            tools=allowed_tools,
            return_intermediate_steps=True,
            verbose=True
        )

        out = agent_executor(agent_input)
        return out
    

    def execute_memory_chain(self, agent_input, prompt_prefix, prompt_suffix):
        
        # memory chain (second step)

        from langchain.prompts import PromptTemplate

        memory_prompt = PromptTemplate(
            template = prompt_prefix + prompt_suffix,
            input_variables=[
                "input",
                "chat_history",
                "episodic_memory",
                "declarative_memory",
            ]
        )

        memory_chain = LLMChain(
            prompt=memory_prompt,
            llm=self.cat.llm,
            verbose=True
        )

        out = memory_chain(agent_input)
        out["output"] = out["text"]
        return out


    def execute_agent(self, agent_input):
        """Instantiate the Agent with tools.

        The method formats the main prompt and gather the allowed tools. It also instantiates a conversational Agent
        from Langchain.

        Returns
        -------
        agent_executor : AgentExecutor
            Instance of the Agent provided with a set of tools.
        """
        mad_hatter = self.cat.mad_hatter

        prompt_prefix = mad_hatter.execute_hook("agent_prompt_prefix")
        prompt_format_instructions = mad_hatter.execute_hook("agent_prompt_instructions")
        prompt_suffix = mad_hatter.execute_hook("agent_prompt_suffix")

        input_variables = [
            "input",
            "chat_history",
            "episodic_memory",
            "declarative_memory",
            "agent_scratchpad",
        ]

        input_variables = mad_hatter.execute_hook("before_agent_creates_prompt", input_variables,
                                                  " ".join([prompt_prefix, prompt_format_instructions, prompt_suffix]))

        allowed_tools = mad_hatter.execute_hook("agent_allowed_tools")
        
        tools_are_enough = False
        if len(allowed_tools) > 0:
            out = self.execute_tool_agent(agent_input, allowed_tools)
            tools_are_enough = out["output"] != "?"

        if not tools_are_enough:
            out = self.execute_memory_chain(agent_input, prompt_prefix, prompt_suffix)

        return out
