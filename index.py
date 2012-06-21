import json, imaplib, email, re, time, datetime, smtplib, json
from email.MIMEMultipart import MIMEMultipart
from email.MIMEText import MIMEText
from email.MIMEBase import MIMEBase

from flask import Flask, render_template, jsonify, request, redirect
import mongoengine as mongo

from secret import EmailCredentials

def connect():
    return mongo.connect('gardn')

def getCurrentUser():
    return User.objects.get_or_create(email=EmailCredentials.ADDRESS)[0]

def sendMail(subject, msg_html, recipient):
    gmailUser = EmailCredentials.ADDRESS;
    gmailPassword = EmailCredentials.PASSWORD;
    msg = MIMEMultipart()
    msg['From'] = gmailUser
    msg['To'] = recipient
    msg['Subject'] = subject

    html = MIMEBase("text", "html")
    html.set_payload(msg_html)
    msg.attach(html)

    mailServer = smtplib.SMTP('smtp.gmail.com', 587)
    mailServer.ehlo()
    mailServer.starttls()
    mailServer.ehlo()
    mailServer.login(gmailUser, gmailPassword)
    mailServer.sendmail(gmailUser, recipient, msg.as_string())
    mailServer.close()
    print('Sent email to %s' % recipient)

class User(mongo.Document):
    email = mongo.StringField(unique=True)
    full_name = mongo.StringField()

class Message(mongo.Document):
    gm_msg_id = mongo.IntField(unique=True)
    gm_thread_id = mongo.IntField()
    message_raw = mongo.StringField()
    date = mongo.DateTimeField()
    from_user = mongo.ReferenceField(User)
    to_users = mongo.ListField(mongo.ReferenceField(User))

    def getBody(self):
        return email.message_from_string(str(self.message_raw))

    def getBodyField(self, field):
        body = self.getBody()
        return body[field]

    def getPayload(self):
        body = self.getBody()
        payloads = body.get_payload()
        for payload in payloads:
            if payload.get_content_type() == 'text/html':
                return payload.get_payload()
        
        return payloads[0].get_payload()

class Discussion(mongo.Document):
    gm_thread_id = mongo.IntField(unique=True)
    subject = mongo.StringField()
    messages = mongo.SortedListField(mongo.ReferenceField(Message))
    participants = mongo.ListField(mongo.ReferenceField(User))

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

            body = email.message_from_string(str(message_raw))
            date_str = body['date']
            date_tuple = email.utils.parsedate(date_str)
            t = time.mktime(date_tuple)
            date = datetime.datetime.fromtimestamp(int(t))

            recipients = body.get_all('to', [])
            recipient_addresses = email.utils.getaddresses(recipients)

            real_recipients = []
            for name, addr in recipient_addresses:
                (recipient, _) = User.objects.get_or_create(email=addr)
                recipient.full_name = name
                recipient.save()
                real_recipients.append(recipient)

            (name, from_address) = email.utils.parseaddr(body['from'])
            (from_user, _) = User.objects.get_or_create(email=from_address)

            (msg_raw, _) = Message.objects.get_or_create(gm_msg_id=id_parsed['gm_msg_id'])
            msg_raw.gm_thread_id = id_parsed['gm_thread_id']
            msg_raw.message_raw = message_raw
            msg_raw.date = date
            msg_raw.to_users = real_recipients
            msg_raw.from_user = from_user
            msg_raw.save()
            
            #FIXME: how to set subject to newest?
            disc_params = {'messages': [], 'subject': msg_raw.getBodyField('Subject')}
            (discussion, created) = Discussion.objects.get_or_create(gm_thread_id=id_parsed['gm_thread_id'], defaults=disc_params)
            discussion.messages.append(msg_raw)
            discussion.participants = [from_user] + real_recipients
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
    msgs = Message.objects(gm_thread_id=gm_thread_id).order_by('date')
    return render_template('discussion.jinja', msgs=msgs, discussion=discussion)

@app.route('/discussion/<gm_thread_id>/reply', methods=['GET', 'POST'])
def reply(gm_thread_id):
    connect()

    if request.method == 'POST':
        discussion = Discussion.objects.get(gm_thread_id=gm_thread_id)
        sendMail(discussion.subject, request.form['message'], "eli.m.goodman@gmail.com")
        return redirect("/")
    else:
        return render_template('reply.jinja')

if __name__ == '__main__':
    app.run(debug=True)
