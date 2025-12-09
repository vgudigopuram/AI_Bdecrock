import json
import uuid
import boto3
import botocore
import os
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

console = Console()

# ------------------------------------------------------
# REQUIRED VARIABLES (YOU MUST UPDATE THESE)
# ------------------------------------------------------
REGION = "us-east-1"
AGENT_ID = "YOUR_AGENT_ID"
AGENT_ALIAS_ID = "YOUR_ALIAS_ID"

# ------------------------------------------------------
# BOTO3 CLIENT WITH SAFE TIMEOUTS
# ------------------------------------------------------
config = botocore.config.Config(
    read_timeout=300,
    connect_timeout=60,
    retries={"max_attempts": 5}
)

bedrock = boto3.client(
    "bedrock-agent-runtime",
    region_name=REGION,
    config=config
)

# ------------------------------------------------------
# PRETTY PANEL FUNCTION
# ------------------------------------------------------
def pretty_panel(title, content, style="cyan"):
    if not content or content.strip() == "":
        content = "[dim]No data available[/dim]"
    console.print(Panel.fit(content, title=title, border_style=style))

# ------------------------------------------------------
# MAIN
# ------------------------------------------------------
def main():
    session_id = f"session-{uuid.uuid4()}"

    # Updated user input for security baseline
    user_input = "Generate security baseline requirements for AWS EC2 service and validate them"

    console.print(f"\n[bold green]▶ START InvokeAgent (session {session_id})[/bold green]\n")
    console.print(f"[dim]Input: {user_input}[/dim]\n")

    try:
        response = bedrock.invoke_agent(
            agentId=AGENT_ID,
            agentAliasId=AGENT_ALIAS_ID,
            sessionId=session_id,
            inputText=user_input,
        )
    except Exception as e:
        console.print(f"[bold red]❌ ERROR calling Bedrock Agent:[/bold red] {e}")
        return

    # Initialize variables to collect data
    model_inputs = []
    model_outputs = []
    rationales = []
    tool_calls = []
    lambda_outputs = []
    metadata_list = []
    final_response = ""

    # ------------------------------------------------------
    # PROCESS STREAM EVENTS WITH BETTER PARSING
    # ------------------------------------------------------
    console.print("[yellow]📡 Processing agent response stream...[/yellow]\n")
    
    for event in response.get("completion", []):
        
        # Debug: Print event structure
        # console.print(f"[dim]Event keys: {list(event.keys())}[/dim]")
        
        # ----- Agent final response text -----
        if "chunk" in event:
            chunk_data = event["chunk"]
            if "bytes" in chunk_data:
                raw = chunk_data["bytes"]
                try:
                    decoded = raw.decode("utf-8")
                    final_response += decoded
                    console.print(f"[green]📝 Agent response chunk: {decoded[:100]}...[/green]")
                except Exception as e:
                    console.print(f"[red]Failed to decode chunk: {e}[/red]")

        # ----- Trace data (this is where the issue was) -----
        elif "trace" in event:
            trace = event["trace"]
            
            # Debug trace structure
            console.print(f"[dim]Trace keys: {list(trace.keys())}[/dim]")
            
            # Check for orchestration trace
            if "orchestrationTrace" in trace:
                orch = trace["orchestrationTrace"]
                console.print(f"[dim]Orchestration trace keys: {list(orch.keys())}[/dim]")
                
                # MODEL INPUT - Fixed structure
                if "modelInvocationInput" in orch:
                    model_inv_input = orch["modelInvocationInput"]
                    if "text" in model_inv_input:
                        model_input = model_inv_input["text"]
                        model_inputs.append(model_input)
                        console.print(f"[blue]🧠 Captured model input: {model_input[:100]}...[/blue]")

                # MODEL OUTPUT - Fixed structure  
                if "modelInvocationOutput" in orch:
                    model_inv_output = orch["modelInvocationOutput"]
                    if "rawResponse" in model_inv_output:
                        model_output = model_inv_output["rawResponse"]
                        model_outputs.append(model_output)
                        console.print(f"[cyan]📤 Captured model output: {model_output[:100]}...[/cyan]")

                # RATIONALE - Fixed structure
                if "rationale" in orch:
                    rat_data = orch["rationale"]
                    if "text" in rat_data:
                        rationale = rat_data["text"]
                        rationales.append(rationale)
                        console.print(f"[yellow]🧐 Captured rationale: {rationale[:100]}...[/yellow]")

                # TOOL CALL INPUT - Fixed structure
                if "actionGroupInvocationInput" in orch:
                    tool_call_data = orch["actionGroupInvocationInput"]
                    tool_calls.append(tool_call_data)
                    console.print(f"[magenta]🛠 Captured tool call[/magenta]")

                # LAMBDA OUTPUT - Fixed structure
                if "actionGroupInvocationOutput" in orch:
                    lambda_out_data = orch["actionGroupInvocationOutput"]
                    lambda_outputs.append(lambda_out_data)
                    console.print(f"[green]📥 Captured lambda output[/green]")

    console.print("\n[yellow]✅ Stream processing complete[/yellow]\n")

    # ------------------------------------------------------
    # RENDER HUMAN-READABLE OUTPUT WITH COLLECTED DATA
    # ------------------------------------------------------
    console.print("=" * 80 + "\n")

    # MODEL INPUTS
    if model_inputs:
        combined_input = "\n\n".join(model_inputs)
        pretty_panel("🧠 MODEL INPUT", combined_input)
    else:
        pretty_panel("🧠 MODEL INPUT", "[red]No model input captured[/red]")

    # MODEL OUTPUTS  
    if model_outputs:
        combined_output = "\n\n".join(model_outputs)
        pretty_panel("📤 MODEL OUTPUT", combined_output)
    else:
        pretty_panel("📤 MODEL OUTPUT", "[red]No model output captured[/red]")

    # RATIONALES
    if rationales:
        combined_rationale = "\n\n".join(rationales)
        pretty_panel("🧐 LLM RATIONALE", combined_rationale, style="yellow")
    else:
        pretty_panel("🧐 LLM RATIONALE", "[red]No rationale captured[/red]", style="yellow")

    # TOOL CALL DETAILS
    if tool_calls:
        for i, tool_call in enumerate(tool_calls, 1):
            table = Table(title=f"Lambda Tool Call #{i}", show_header=True, header_style="bold magenta")
            table.add_column("Field", style="cyan")
            table.add_column("Value", style="white")

            table.add_row("Action Group", str(tool_call.get("actionGroupName", "N/A")))
            table.add_row("Function", str(tool_call.get("function", "N/A")))
            table.add_row("Execution Type", str(tool_call.get("executionType", "N/A")))

            # Handle parameters properly
            params = tool_call.get("parameters", [])
            if params:
                try:
                    params_str = json.dumps(params, indent=2)
                except:
                    params_str = str(params)
            else:
                params_str = "No parameters"
            
            table.add_row("Parameters", params_str)
            console.print(table)
    else:
        console.print("[dim]No tool calls captured[/dim]")

    # LAMBDA OUTPUTS
    if lambda_outputs:
        for i, lambda_out in enumerate(lambda_outputs, 1):
            output_text = lambda_out.get("text", "")
            if not output_text:
                output_text = str(lambda_out)
            
            try:
                # Try to format as JSON if possible
                parsed = json.loads(output_text)
                syntax = Syntax(json.dumps(parsed, indent=2), "json", theme="monokai", line_numbers=False)
                pretty_panel(f"🛠 LAMBDA RESPONSE #{i}", syntax, style="green")
            except:
                pretty_panel(f"🛠 LAMBDA RESPONSE #{i}", output_text, style="green")
    else:
        console.print("[dim]No lambda outputs captured[/dim]")

    # FINAL AGENT RESPONSE
    if final_response:
        pretty_panel("✅ FINAL RESPONSE", final_response, style="bright_green")
    else:
        pretty_panel("✅ FINAL RESPONSE", "[red]No final response captured[/red]", style="bright_green")

    console.print("\n[bold green]✔ FINISHED InvokeAgent[/bold green]\n")

    # Summary
    console.print("[bold blue]📊 SUMMARY:[/bold blue]")
    console.print(f"  • Model Inputs: {len(model_inputs)}")
    console.print(f"  • Model Outputs: {len(model_outputs)}")
    console.print(f"  • Rationales: {len(rationales)}")
    console.print(f"  • Tool Calls: {len(tool_calls)}")
    console.print(f"  • Lambda Outputs: {len(lambda_outputs)}")
    console.print(f"  • Final Response Length: {len(final_response)} characters")

# ------------------------------------------------------
if __name__ == "__main__":
    main()
