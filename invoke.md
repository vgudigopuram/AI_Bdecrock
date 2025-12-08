import json
import uuid
import boto3
import os
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

console = Console()

REGION = os.environ.get("REGION")
AGENT_ID = os.environ.get("AGENT_ID")
AGENT_ALIAS_ID = os.environ.get("AGENT_ALIAS_ID")

bedrock = boto3.client("bedrock-agent-runtime", region_name=REGION)


def pretty_panel(title, content, style="cyan"):
    console.print(Panel.fit(content, title=title, border_style=style))


def main():
    session_id = f"session-{uuid.uuid4()}"

    user_input = "Create a VPC with CIDR 10.0.0.0/16 and return the IDs."

    console.print(f"\n[bold green]▶ START InvokeAgent (session {session_id})[/bold green]\n")

    response = bedrock.invoke_agent(
        agentId=AGENT_ID,
        agentAliasId=AGENT_ALIAS_ID,
        sessionId=session_id,
        inputText=user_input,
    )

    model_input = ""
    model_output = ""
    rationale = ""
    tool_call = {}
    lambda_output = ""
    metadata = {}
    final_response = ""

    # -------- PROCESS STREAMED EVENTS --------
    for event in response.get("completion", []):

        if "chunk" in event:
            # agent output tokens
            text = event["chunk"]["bytes"]
            try:
                final_response += text.decode()
            except:
                final_response += text

        elif "trace" in event:
            trace = event["trace"]
            orch = trace.get("orchestrationTrace", {})

            # Model Input
            model_input = orch.get("modelInvocationInput", {}).get("text", "")

            # Model Output
            model_output = orch.get("modelInvocationOutput", {}).get("rawResponse", "")

            # Rationale
            rationale = orch.get("rationale", {}).get("text", "")

            # Tool invocation
            ag_in = orch.get("actionGroupInvocationInput", {})
            tool_call = ag_in.get("actionGroupInvocationInput", {})

            # Lambda output
            ag_out = orch.get("actionGroupInvocationOutput", {})
            lambda_output = ag_out.get("actionGroupInvocationOutput", {}).get("text", "")

            # Metadata
            metadata = ag_out.get("actionGroupInvocationOutput", {}).get("metadata", {})

    # -------- DISPLAY BEAUTIFUL OUTPUT --------

    pretty_panel("🧠 MODEL INPUT", model_input)
    pretty_panel("📤 MODEL OUTPUT", model_output)
    pretty_panel("🧐 MODEL RATIONALE", rationale, style="yellow")

    # TOOL CALL
    if tool_call:
        table = Table(title="Lambda Tool Call Details", show_header=True, header_style="bold magenta")
        table.add_column("Field")
        table.add_column("Value")

        table.add_row("Action Group", tool_call.get("actionGroupName", ""))
        table.add_row("Function", tool_call.get("function", ""))
        table.add_row("Execution Type", tool_call.get("executionType", ""))

        params = json.dumps(tool_call.get("parameters", []), indent=2)
        table.add_row("Parameters", params)

        console.print(table)

    # Lambda output
    if lambda_output:
        syntax = Syntax(lambda_output, "json", theme="monokai", line_numbers=False)
        pretty_panel("🛠 LAMBDA RESPONSE", syntax, style="green")

    # Metadata
    if metadata:
        pretty_panel("⏱ EXECUTION METADATA", json.dumps(metadata, indent=2))

    # Final response
    pretty_panel("✅ FINAL RESPONSE", final_response, style="bright_green")

    console.print("\n[bold green]✔ FINISHED InvokeAgent[/bold green]\n")


if __name__ == "__main__":
    main()
