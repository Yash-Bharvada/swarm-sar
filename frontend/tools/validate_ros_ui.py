"""Browser contract test with explicitly SYNTHETIC rosbridge fixtures.

Requires Python Playwright and its Chromium installation. Start Vite separately.
This does not validate ROS, SLAM, Gazebo or the actual PPO controller.
"""
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--url',default='http://127.0.0.1:5178/?mode=ros')
    parser.add_argument('--output',default='artifacts/slam_local_ui')
    parser.add_argument('--browser-executable',default=None)
    args=parser.parse_args(); output=Path(args.output); output.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,executable_path=args.browser_executable)
        page=browser.new_page(viewport=dict(width=1440,height=1000))
        errors=[]; page.on('pageerror',lambda e:errors.append(str(e)))
        routes=[]; requests=[]
        def route(ws):
            routes.append(ws)
            def receive(data):
                message=json.loads(data); requests.append(message)
                if message.get('op')=='call_service':
                    success=message['args']['data'] is True
                    ws.send(json.dumps(dict(op='service_response',id=message['id'],result=success,
                        values=dict(success=success,message='SYNTHETIC acknowledgement' if success else 'SYNTHETIC service rejected'))))
            ws.on_message(receive)
        page.route_web_socket('ws://fixture.invalid:9090/',route)
        page.goto(args.url)
        expect(page.get_by_text('Waiting for real ROS map messages…')).to_have_count(0)  # canvas text, not fabricated DOM telemetry
        expect(page.get_by_text('disconnected · WAITING / STALE')).to_be_visible()
        expect(page.get_by_role('button',name='Isolate rover_0')).to_be_disabled()
        page.screenshot(path=str(output/'disconnected_real_ui.png'),full_page=True)
        page.get_by_label('ROS bridge URL').fill('ws://fixture.invalid:9090')
        page.get_by_role('button',name='Connect',exact=True).click()
        page.wait_for_function("document.body.innerText.includes('connected · WAITING / STALE')")
        assert routes,'rosbridge socket was not opened'
        def send(topic,msg):routes[0].send(json.dumps(dict(op='publish',topic=topic,msg=msg)))
        send('/clock',dict(clock=dict(sec=10,nanosec=0)))
        origin=dict(position=dict(x=0,y=0),orientation=dict(x=0,y=0,z=0,w=1))
        grid=dict(header=dict(frame_id='map'),info=dict(width=8,height=8,resolution=1,origin=origin),data=[-1]*64)
        grid['data'][9]=100; grid['data'][10]=0
        send('/rover_0/local_slam_map',grid)
        send('/rover_0/slam_health',dict(data=json.dumps(dict(agent='rover_0',run='SYNTHETIC-UI-TEST',state='tracking',source='slam_toolbox',
            sim_time=10,local_known=2,peer_known=1,map_age=.1,pose_age=.1,peers={}))))
        stats=dict(sim_time=10,metrics=dict(delivered=4),isolated=[],queue=0,reset_required=False,bytes_per_second=32768)
        send('/swarm/network/stats',dict(data=json.dumps(stats)))
        send('/rover_0/estimated_odom',dict(header=dict(frame_id='map'),pose=dict(pose=dict(position=dict(x=1,y=1),orientation=dict(z=0,w=1)))))
        expect(page.get_by_text('connected · LIVE')).to_be_visible()
        page.get_by_role('button',name='Isolate rover_0').click()
        expect(page.get_by_text('ROS acknowledged the request.',exact=False)).to_be_visible()
        # Service success alone must not fabricate the radio's observed state.
        expect(page.get_by_text('Status: radio enabled')).to_be_visible()
        assert any(m.get('service')=='/swarm/network/isolate/rover_0' and m.get('args')==dict(data=True) for m in requests)
        stats['isolated']=['rover_0']; send('/swarm/network/stats',dict(data=json.dumps(stats)))
        expect(page.get_by_role('button',name='Reconnect rover_0')).to_be_visible()
        page.get_by_role('button',name='Reconnect rover_0').click()
        expect(page.get_by_text('SYNTHETIC service rejected')).to_be_visible()
        expect(page.get_by_text('Status: ISOLATED')).to_be_visible()
        page.get_by_role('button',name='Disconnect',exact=True).click()
        expect(page.get_by_text('disconnected · WAITING / STALE')).to_be_visible()
        expect(page.get_by_role('button',name='Reconnect rover_0')).to_be_disabled()
        assert not errors,errors
        assert not any(m.get('op')=='publish' for m in requests),'operator UI must never publish control/map commands'
        browser.close()
    report=dict(passed=True,kind='synthetic_rosbridge_browser_contract',
        checks=['disconnected waiting state','real socket subscriptions','incoming map/pose/health handling','service request payload',
                'service acknowledgement does not fabricate isolation status','service failure is visible and preserves observed state',
                'status follows received telemetry','disconnect disables radio controls','no control publications','no browser errors'],
        limits='Synthetic fixtures only: not live ROS/Gazebo/SLAM/PPO evidence.')
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n'); print(json.dumps(report,indent=2))


if __name__=='__main__':main()
