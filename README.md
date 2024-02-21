# LSL-data-player
To play recorded data to the LabStreamingLayer. Useful for real-time simulation and debugging. One may combine this player with an LSL signal viewer (e.g., https://github.com/nafraw/Signal-Viewer-for-multi-streams) to check whether it works.

# How to use
You need to have your data ready in the csv format. An instance is the provided sample_data.csv.
1. Choose whether to use a single stream or multi-stream player
2. Based on 1, revise the corresponding .ini file (read the comments in the ini file)
3. Make sure the ini file is in the same folder of the script of exe and the path to the csv file is correct
4. Run the python script or exe

The released exe file is likely to run only on a Windows 64 machine. If you wish to compile for a different system. Use pyinstaller with the command:\
"pyinstaller multi_stream_player.spec" or\
"pyinstaller single_stream_player.spec"
