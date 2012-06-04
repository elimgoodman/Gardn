import json, imaplib, email, re

from flask import Flask, render_template, jsonify, request, redirect
import mongoengine as mongo

from secret import EmailCredentials

def connect():
    return mongo.connect('gardn')

class MessageRaw(mongo.Document):
    gm_msg_id = mongo.IntField(unique=True)
    gm_thread_id = mongo.IntField()
    message_raw = mongo.StringField()

    def getBody(self):
        return email.message_from_string(str(self.message_raw))

app = Flask(__name__)

@app.route('/refresh')
def refresh():
    connect()

    mail = imaplib.IMAP4_SSL('imap.gmail.com')
    mail.login(EmailCredentials.ADDRESS, EmailCredentials.PASSWORD)
    mail.select("inbox")
    
    #all msg uids
    result, data = mail.uid('search', None, "ALL")
    uids = data[0].split()

    for uid in uids:
        result, data = mail.uid('fetch', uid, '(RFC822 X-GM-THRID X-GM-MSGID)')
        msg_data = data[0]
        (id_data, message_raw) = msg_data
        id_parsed = re.search(r'X-GM-THRID (?P<gm_thread_id>\d+) X-GM-MSGID (?P<gm_msg_id>\d+)', id_data).groupdict()
        params = {'gm_thread_id': id_parsed['gm_thread_id'], 'message_raw': message_raw}
        MessageRaw.objects.get_or_create(gm_msg_id=id_parsed['gm_msg_id'], defaults=params)

    return redirect("/")

@app.route('/')
def index():
    connect()
    
    msgs = MessageRaw.objects()
    emails = []
    for msg in msgs:
        emails.append({
            'body': msg.getBody(),
            'msg': msg
        })
    return render_template('index.jinja', emails=emails)


@app.route('/discussion/<gm_thread_id>')
def discussion(gm_thread_id):
    connect()
    
    msgs = MessageRaw.objects(gm_thread_id=gm_thread_id)
    return render_template('discussion.jinja', msgs=msgs)

if __name__ == '__main__':
    app.run(debug=True)
