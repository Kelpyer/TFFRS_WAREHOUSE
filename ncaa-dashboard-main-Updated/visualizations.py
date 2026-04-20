import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator

# Set Styles
sns.set_style('whitegrid')
sns.set_palette('muted')


def plot_time_progression(df, event_filter):
    """
    Returns a progression graph for the selected event.
    - Track events: plots Time_seconds (lower = better, y-axis inverted)
    - Field events: plots Mark_meters (higher = better, y-axis normal)
    """
    df_event = df[df['Event'] == event_filter].copy()

    # Determine event type
    event_type = df_event['Event_Type'].iloc[0] if len(df_event) > 0 else 'Track'

    if event_type == 'Field':
        df_event = df_event.dropna(subset=['Mark_meters', 'Race_Date'])
        df_event = df_event.sort_values('Race_Date')
        y_col = 'Mark_meters'
        y_label = 'Distance (meters)'
        title = f'{event_filter} Distance Progression'
        invert = False
        best_row = df_event.loc[df_event[y_col].idxmax()] if len(df_event) > 0 else None
        best_label = 'Best Throw'
    else:
        df_event = df_event.dropna(subset=['Time_seconds', 'Race_Date'])
        df_event = df_event.sort_values('Race_Date')
        y_col = 'Time_seconds'
        y_label = 'Time (seconds)'
        title = f'{event_filter} Time Progression'
        invert = True
        best_row = df_event.loc[df_event[y_col].idxmin()] if len(df_event) > 0 else None
        best_label = 'Fastest Time'

    fig, ax = plt.subplots(figsize=(12, 6))

    if df_event.empty:
        ax.text(0.5, 0.5, 'No valid data for this event', ha='center', va='center', transform=ax.transAxes)
        return fig

    sns.lineplot(data=df_event, x='Race_Date', y=y_col, marker='o', linewidth=2.5, ax=ax)

    if invert:
        ax.invert_yaxis()

    ax.set_title(title, fontsize=16)
    ax.set_xlabel('Date', fontsize=14)
    ax.set_ylabel(y_label, fontsize=14)
    ax.grid(axis='y', linestyle='--', alpha=0.7)

    offset = -0.1 if invert else 0.1
    for i, row in df_event.iterrows():
        ax.text(row['Race_Date'], row[y_col] + offset, row['Mark'],
                ha='center', va='bottom', fontsize=9, color='black')

    if best_row is not None:
        ax.scatter(best_row['Race_Date'], best_row[y_col],
                   color='red', s=100, edgecolor='black', zorder=5, label=best_label)

    ax.legend(title='Legend', fontsize=12, title_fontsize=13)

    return fig


def plot_placement_distribution(df):
    placement_counts = df['Placement_Number'].value_counts().sort_index()
    num_no_placement = df['Placement_Number'].isna().sum()

    placement_df = pd.DataFrame({
        'Placement': placement_counts.index.astype(int).astype(str),
        'Count': placement_counts.values
    })

    placement_df = pd.concat([
        placement_df,
        pd.DataFrame({'Placement': ['No Placement'], 'Count': [num_no_placement]})
    ], ignore_index=True)

    numeric_placements = sorted(set(int(p) for p in placement_df['Placement'] if p != 'No Placement'))
    numeric_placements = [str(p) for p in numeric_placements]

    placement_df['Placement'] = pd.Categorical(
        placement_df['Placement'],
        categories=numeric_placements + ['No Placement'],
        ordered=True
    )
    placement_df = placement_df.sort_values('Placement')

    fig, ax = plt.subplots(figsize=(12, 6))

    sns.barplot(data=placement_df, x='Placement', y='Count', hue='Placement',
                palette='muted', edgecolor='black', legend=False, ax=ax)

    ax.set_title('Placement Distribution Across All Races', fontsize=16)
    ax.set_xlabel('Finish Position', fontsize=14)
    ax.set_ylabel('Number of Races', fontsize=14)
    ax.yaxis.set_major_locator(MaxNLocator(integer=True))
    plt.xticks(rotation=0)

    return fig
