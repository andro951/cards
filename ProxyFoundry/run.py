"""Double-click START_PROXY_FOUNDRY.bat on Windows; python run.py elsewhere."""
import argparse,threading,webbrowser
from foundry.server import App,LocalServer
from foundry.storage import Store,ensure_storage_home_selected

def main():
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=0);p.add_argument('--no-browser',action='store_true');a=p.parse_args()
    home=ensure_storage_home_selected()
    app=App(store=Store(home));server=LocalServer(app,a.port)
    print('\nBULK PROXY FORGE\n'+server.origin+'\nWorkspace: '+str(app.store.home)+'\nKeep this window open. Press Ctrl+C to stop.\n',flush=True)
    if not a.no_browser:threading.Timer(.7,lambda:webbrowser.open(server.origin,new=2)).start()
    try:server.serve_forever(poll_interval=.2)
    except KeyboardInterrupt:print('\nStopping. Saved decks and completed images are safe.')
    finally:app.close();server.server_close()
if __name__=='__main__':main()
