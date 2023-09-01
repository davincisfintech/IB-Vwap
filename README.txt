***  Installation ***

install python 3.10/3.11 for your operating system using this link  https://www.python.org/downloads/

install pycharm community edition using this link  https://www.jetbrains.com/pycharm/download/


*** Setup  ***

run following commands from command prompt/terminal

for MacOs/Linux:

      cd < project directory>    # move to project directory, for ex. if project folder location is C:\Users\Td-Bot then command will be: cd C:\Users\IB-Options-Bot
      python -m venv venv        # create virtual environment
      source venv/bin/activate       # activate virtual environment
      pip install -r requirements.txt    # install dependencies

for windows:

       cd < project directory>    # move to project directory, for ex. if project folder location is C:\Users\Td-Bot then command will be: cd C:\Users\IB-Options-Bot
       python -m venv venv        # create virtual environment
       venv\Scripts\activate      # activate virtual environment
       pip install -r requirements.txt     # install dependencies


*** Parameters ***

provide your parameters in main.py file as instructed in it


*** How To Run ***
Make sure IB TWS is open when running program

Option 1:
    To run using pycharm:

    set main.py located in main folder in pycharm configuration and click on run button to run program

Option 2:
    To run using terminal:

    run following commands from command prompt/terminal

    for MacOs/Linux:
          cd < project directory>           # move to project directory
          source venv/bin/activate         # activate virtual environment
          python main.py    # Run program

    for windows:
           cd < project directory>           # move to project directory
           venv\Scripts\activate            # activate virtual environment
           main.py       # Run program


***  Logs  ***
date wise log file will be created inside logs folder to show status of program


*** Results ***

all trades will be stored in database and they can be exported to excel by running metrics.py

