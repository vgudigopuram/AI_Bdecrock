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
    final_response = ""

    # ------------------------------------------------------
    # PROCESS STREAM EVENTS WITH CORRECT PARSING
    # ------------------------------------------------------
    console.print("[yellow]📡 Processing agent response stream...[/yellow]\n")
    
    for event in response.get("completion", []):
        
        # Debug: Print event structure
        console.print(f"[dim]Event keys: {list(event.keys())}[/dim]")
        
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

        # ----- Trace data (FIXED PARSING) -----
        elif "trace" in event:
            trace = event["trace"]
            
            # Debug trace structure
            console.print(f"[dim]Trace keys: {list(trace.keys())}[/dim]")
            
            # Check for orchestration trace
            if "orchestrationTrace" in trace:
                orch = trace["orchestrationTrace"]
                console.print(f"[dim]Orchestration trace keys: {list(orch.keys())}[/dim]")
                
                # MODEL INPUT - Direct access
                if "modelInvocationInput" in orch:
                    model_inv_input = orch["modelInvocationInput"]
                    console.print(f"[dim]ModelInvocationInput keys: {list(model_inv_input.keys())}[/dim]")
                    
                    if "text" in model_inv_input:
                        model_input = model_inv_input["text"]
                        model_inputs.append(model_input)
                        console.print(f"[blue]🧠 Captured model input: {model_input[:100]}...[/blue]")
                    else:
                        console.print(f"[red]No 'text' field in modelInvocationInput: {model_inv_input}[/red]")

                # MODEL OUTPUT - Direct access
                if "modelInvocationOutput" in orch:
                    model_inv_output = orch["modelInvocationOutput"]
                    console.print(f"[dim]ModelInvocationOutput keys: {list(model_inv_output.keys())}[/dim]")
                    
                    if "rawResponse" in model_inv_output:
                        model_output = model_inv_output["rawResponse"]
                        model_outputs.append(model_output)
                        console.print(f"[cyan]📤 Captured model output: {model_output[:100]}...[/cyan]")
                    else:
                        console.print(f"[red]No 'rawResponse' field in modelInvocationOutput: {model_inv_output}[/red]")

                # RATIONALE - Direct access
                if "rationale" in orch:
                    rat_data = orch["rationale"]
                    console.print(f"[dim]Rationale keys: {list(rat_data.keys())}[/dim]")
                    
                    if "text" in rat_data:
                        rationale = rat_data["text"]
                        rationales.append(rationale)
                        console.print(f"[yellow]🧐 Captured rationale: {rationale[:100]}...[/yellow]")
                    else:
                        console.print(f"[red]No 'text' field in rationale: {rat_data}[/red]")

                # TOOL CALL INPUT - From invocationInput
                if "invocationInput" in orch:
                    invocation_input = orch["invocationInput"]
                    console.print(f"[dim]InvocationInput keys: {list(invocation_input.keys())}[/dim]")
                    
                    if "actionGroupInvocationInput" in invocation_input:
                        tool_call_data = invocation_input["actionGroupInvocationInput"]
                        tool_calls.append(tool_call_data)
                        console.print(f"[magenta]🛠 Captured tool call: {tool_call_data.get('function', 'unknown')}[/magenta]")

                # LAMBDA OUTPUT - From observation
                if "observation" in orch:
                    observation = orch["observation"]
                    console.print(f"[dim]Observation keys: {list(observation.keys())}[/dim]")
                    
                    if "actionGroupInvocationOutput" in observation:
                        lambda_out_data = observation["actionGroupInvocationOutput"]
                        lambda_outputs.append(lambda_out_data)
                        console.print(f"[green]📥 Captured lambda output[/green]")
                    
                    # FINAL RESPONSE - From observation
                    if "finalResponse" in observation:
                        final_resp = observation["finalResponse"]
                        if isinstance(final_resp, str):
                            final_response += final_resp
                        else:
                            final_response += str(final_resp)
                        console.print(f"[bright_green]✅ Captured final response[/bright_green]")

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
            table = Table(title=f"🛠 Lambda Tool Call #{i}", show_header=True, header_style="bold magenta")
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
        console.print("[dim]🛠 No tool calls captured[/dim]")

    # LAMBDA OUTPUTS
    if lambda_outputs:
        for i, lambda_out in enumerate(lambda_outputs, 1):
            output_text = lambda_out.get("text", "")
            if not output_text:
                output_text = str(lambda_out)
            
            # Show metadata if available
            metadata = lambda_out.get("metadata", {})
            
            try:
                # Try to format as JSON if possible
                parsed = json.loads(output_text)
                syntax = Syntax(json.dumps(parsed, indent=2), "json", theme="monokai", line_numbers=False)
                pretty_panel(f"📥 LAMBDA RESPONSE #{i}", syntax, style="green")
            except:
                pretty_panel(f"📥 LAMBDA RESPONSE #{i}", output_text, style="green")
            
            # Show metadata in a table
            if metadata:
                meta_table = Table(title=f"Metadata for Response #{i}", show_header=True)
                meta_table.add_column("Field", style="cyan")
                meta_table.add_column("Value", style="white")
                
                for key, value in metadata.items():
                    meta_table.add_row(str(key), str(value))
                
                console.print(meta_table)
    else:
        console.print("[dim]📥 No lambda outputs captured[/dim]")

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
