#!/usr/bin/env python3
"""
Generate architectural diagram for the RAG Pipeline system using matplotlib.
"""

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from matplotlib.backends.backend_pdf import PdfPages

def create_architecture_diagram():
    """Create a high-level architectural diagram of the RAG system."""

    # Create figure
    fig, ax = plt.subplots(1, 1, figsize=(16, 12))
    ax.set_xlim(0, 16)
    ax.set_ylim(0, 12)
    ax.axis('off')

    # Title
    ax.text(8, 11.5, 'RAG Pipeline Architecture',
            ha='center', va='top', fontsize=20, fontweight='bold')

    # Define colors
    interface_color = '#E3F2FD'  # Light blue
    core_color = '#FFF3E0'       # Light orange
    storage_color = '#F3E5F5'    # Light purple
    external_color = '#E8F5E9'   # Light green

    def draw_box(x, y, width, height, text, color, fontsize=10):
        """Draw a rounded rectangle box with text."""
        box = FancyBboxPatch(
            (x, y), width, height,
            boxstyle="round,pad=0.05",
            facecolor=color, edgecolor='black', linewidth=1.5
        )
        ax.add_patch(box)
        ax.text(x + width/2, y + height/2, text,
                ha='center', va='center', fontsize=fontsize, fontweight='bold')

    def draw_arrow(x1, y1, x2, y2, label='', style='solid', color='black'):
        """Draw an arrow between two points."""
        arrow = FancyArrowPatch(
            (x1, y1), (x2, y2),
            arrowstyle='->', mutation_scale=20,
            linestyle=style, linewidth=1.5, color=color
        )
        ax.add_patch(arrow)
        if label:
            mid_x, mid_y = (x1 + x2) / 2, (y1 + y2) / 2
            ax.text(mid_x, mid_y, label, fontsize=8,
                   bbox=dict(boxstyle='round,pad=0.3', facecolor='white', edgecolor='none'),
                   ha='center', va='center')

    def draw_group(x, y, width, height, label):
        """Draw a group box."""
        box = FancyBboxPatch(
            (x, y), width, height,
            boxstyle="round,pad=0.1",
            facecolor='none', edgecolor='gray', linewidth=2, linestyle='--'
        )
        ax.add_patch(box)
        ax.text(x + width/2, y + height - 0.15, label,
                ha='center', va='top', fontsize=11, fontweight='bold', color='gray')

    # ===== LAYER 1: EXTERNAL SERVICES (Top) =====
    draw_group(0.5, 9.5, 15, 1.3, 'External Services')
    draw_box(2, 9.7, 2.5, 0.8, 'Hugging Face\n(Embeddings)', external_color)
    draw_box(11.5, 9.7, 2.5, 0.8, 'OpenAI API\n(LLM)', external_color)

    # ===== LAYER 2: USER INTERFACES =====
    draw_group(0.5, 7.8, 15, 1.3, 'User Interfaces')
    draw_box(2, 8, 2.5, 0.8, 'CLI\n(Typer)', interface_color)
    draw_box(11.5, 8, 2.5, 0.8, 'Web API\n(FastAPI)', interface_color)

    # ===== LAYER 3: CORE COMPONENTS (rag_core) =====
    draw_group(0.5, 3.5, 15, 4, 'rag_core (Shared Library)')

    # Scanner subsystem
    draw_group(1, 6, 4.5, 1.2, 'Scanner')
    draw_box(1.2, 6.1, 1.9, 0.7, 'File Scanner\n(SHA-256)', core_color, 9)
    draw_box(3.4, 6.1, 1.9, 0.7, 'Chunker\n(Token/MD/Code)', core_color, 9)

    # Vectorizer subsystem
    draw_group(6.5, 6, 3.5, 1.2, 'Vectorizer')
    draw_box(6.7, 6.1, 1.4, 0.7, 'Embedder', core_color, 9)
    draw_box(8.4, 6.1, 1.4, 0.7, 'Batch\nProcessor', core_color, 9)

    # Query Engine
    draw_box(11, 6.1, 3.5, 0.7, 'Query Engine\n(ANN Search + Re-rank)', core_color, 9)

    # LLM subsystem
    draw_group(1, 4.3, 4.5, 1.2, 'LLM Clients')
    draw_box(1.2, 4.4, 1.9, 0.7, 'OpenAI\nClient', core_color, 9)
    draw_box(3.4, 4.4, 1.9, 0.7, 'Anthropic\nClient', core_color, 9)

    # Config
    draw_box(11, 4.4, 3.5, 0.7, 'Config Manager\n(ENV/YAML/CLI)', core_color, 9)

    # ===== LAYER 4: STORAGE =====
    draw_group(0.5, 1.5, 15, 1.7, 'Storage Layer')
    draw_box(3, 1.7, 3, 0.9, 'File Tracker\n(SQLite)', storage_color)
    draw_box(10, 1.7, 3, 0.9, 'Vector Store\n(sqlite-vec)', storage_color)

    # ===== DATA FLOW ARROWS =====

    # User interfaces to scanner
    draw_arrow(3.25, 8, 3.25, 7.2, 'scan')
    draw_arrow(12.75, 8, 12.75, 7.2)

    # Scanner flow
    draw_arrow(3.1, 6.1, 4.3, 6.1, 'files')
    draw_arrow(2.1, 6.1, 4.5, 2.7, 'metadata')
    draw_arrow(5.3, 6.5, 6.7, 6.5, 'chunks')

    # Embedding flow
    draw_arrow(8.1, 6.5, 8.4, 6.5)
    draw_arrow(9.1, 6.8, 3.25, 9.7, 'API')
    draw_arrow(9.1, 6.1, 11.5, 2.3, 'vectors')

    # Query flow
    draw_arrow(12.75, 6.1, 11.5, 2.6, 'search')
    draw_arrow(12.0, 4.4, 12.0, 6.1, 'context')
    draw_arrow(2.1, 5.1, 2.1, 6.1)
    draw_arrow(2.1, 8.0, 2.1, 9.7)
    draw_arrow(12.75, 8.0, 12.75, 9.7, 'LLM call')

    # Config connections (dotted)
    draw_arrow(11.5, 5.1, 7.5, 6.1, style='dotted', color='gray')
    draw_arrow(12.5, 5.1, 12.5, 6.1, style='dotted', color='gray')

    # Add data flow legend
    legend_y = 0.8
    ax.text(1, legend_y, 'Data Flow:', fontsize=10, fontweight='bold')
    ax.plot([1.8, 2.3], [legend_y, legend_y], 'k-', linewidth=1.5)
    ax.arrow(2.3, legend_y, 0.1, 0, head_width=0.08, head_length=0.08, fc='black', ec='black')
    ax.text(2.5, legend_y, 'Primary flow', fontsize=9, va='center')

    ax.plot([4.5, 5.0], [legend_y, legend_y], 'k:', linewidth=1.5)
    ax.arrow(5.0, legend_y, 0.1, 0, head_width=0.08, head_length=0.08, fc='gray', ec='gray')
    ax.text(5.2, legend_y, 'Configuration', fontsize=9, va='center', color='gray')

    # Add processing steps at the bottom
    steps_y = 0.3
    steps = ['1. SCAN', '2. CHUNK', '3. EMBED', '4. RETRIEVE', '5. GENERATE']
    step_colors = [core_color, core_color, core_color, storage_color, external_color]

    for i, (step, color) in enumerate(zip(steps, step_colors)):
        x_pos = 2 + i * 2.5
        draw_box(x_pos, steps_y, 2, 0.4, step, color, 9)
        if i < len(steps) - 1:
            draw_arrow(x_pos + 2, steps_y + 0.2, x_pos + 2.5, steps_y + 0.2)

    plt.tight_layout()
    return fig

def main():
    """Generate and save the architecture diagram as PDF."""
    print("Generating RAG Pipeline architecture diagram...")

    fig = create_architecture_diagram()

    # Save as PDF
    output_file = 'rag_architecture.pdf'
    with PdfPages(output_file) as pdf:
        pdf.savefig(fig, bbox_inches='tight')

    plt.close()

    print(f"✓ Diagram saved as {output_file}")

if __name__ == '__main__':
    main()
