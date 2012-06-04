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

    def getBodyField(self, field):
        body = self.getBody()
        return body[field]

#class Messsage(mongo.EmbeddedDocument):
    #gm_msg_id = mongo.IntField(required=True)
    #content = mongo.StringField()

class Discussion(mongo.Document):
    gm_thread_id = mongo.IntField(unique=True)
    subject = mongo.StringField()
    messages = mongo.SortedListField(mongo.ReferenceField(MessageRaw))

app = Flask(__name__)

@app.route('/refresh')
def refresh():
    connect()

    mail = imaplib.IMAP4_SSL('imap.gmail.com')
    mail.login(EmailCredentials.ADDRESS, EmailCredentials.PASSWORD)
    boxes = ["inbox", "[Gmail]/Sent Mail"]

    for box in boxes:
        mail.select(box)
        
        #all msg uids
        result, data = mail.uid('search', None, "ALL")
        uids = data[0].split()

        for uid in uids:
            result, data = mail.uid('fetch', uid, '(RFC822 X-GM-THRID X-GM-MSGID)')
            msg_data = data[0]
            (id_data, message_raw) = msg_data
            id_parsed = re.search(r'X-GM-THRID (?P<gm_thread_id>\d+) X-GM-MSGID (?P<gm_msg_id>\d+)', id_data).groupdict()
            params = {'gm_thread_id': id_parsed['gm_thread_id'], 'message_raw': message_raw}
            (msg_raw, created) = MessageRaw.objects.get_or_create(gm_msg_id=id_parsed['gm_msg_id'], defaults=params)

            #body = msg_raw.getBody()
            #parts = body.get_payload()
            #FIXME: arbitrary
            #msg = Message(gm_msg_id=id_parsed['gm_msg_id'], content=part[0].get_payload())

            #FIXME: how to set subject to newest?
            disc_params = {'messages': [], 'subject': msg_raw.getBodyField('Subject')}
            (discussion, created) = Discussion.objects.get_or_create(gm_thread_id=id_parsed['gm_thread_id'], defaults=disc_params)
            discussion.messages.append(msg_raw)
            discussion.save()

    return redirect("/")

@app.route('/')
def index():
    connect()
    
    discussions = Discussion.objects()
    return render_template('index.jinja', discussions=discussions)


@app.route('/discussion/<gm_thread_id>')
def discussion(gm_thread_id):
    connect()
    
    discussion = Discussion.objects.get(gm_thread_id=gm_thread_id)
    return render_template('discussion.jinja', discussion=discussion)

if __name__ == '__main__':
    app.run(debug=True)
