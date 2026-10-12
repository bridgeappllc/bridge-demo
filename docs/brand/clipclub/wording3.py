"""Simple-sharing wording pass (no differences/disagreement framing). UI text only."""
P={'index.html':[
 ('Check this out: listen to "${b.clip_title}" in the next 3 days.\\n','Check this out: "${b.clip_title}"\\n'),
 ("\\nThen join me here: we each answer 3 quick questions, then talk about where we see it differently:\\n","\\nListen and let's talk about it on Clip Club:\\n"),
 ("We don't have to agree to understand each other.</p><p class=\"mut\" style=\"font-size:1.05rem\">Listen to the same thing, show you listened, then talk about where you see it differently.",
  "Share what you're listening to.</p><p class=\"mut\" style=\"font-size:1.05rem\">Send a friend a podcast, video or article. You both listen, answer 3 quick questions, then chat."),
 ('<p class="mut">We don\'t have to agree to understand each other.</p>','<p class="mut">Listen together, then talk about it.</p>'),
 ("answer 3 quick questions, then talk about where you see it differently.","answer 3 quick questions, then chat."),
 ("Start the conversation: where do you see it differently?","Start the conversation: what did you think?"),
 ("Their library shows how they see the world.","Their favorite podcasts, videos and articles."),
 ("Your library shows how you see the world. Add the podcasts, videos and articles that shaped your views.","Your favorite clips live here. Add podcasts, videos and articles you love."),
 ("Was there anything said that you strongly agreed or disagreed with? What was it?","Was there anything that surprised you or made you think? What was it?"),
 ("what would you say—and did it change or reinforce how you see the topic?","what would you say?")],
 'privacy.html':[("and talking about where you see it differently.","and chatting about it.")],
 'terms.html':[("Clip Club is for honest conversations between people who see things differently.","Clip Club is for friendly conversations about the things you share.")]}
for f,ps in P.items():
    s=open(f).read()
    for a,b in ps:
        assert a in s,(f,a); s=s.replace(a,b)
    open(f,'w').write(s)
print('ok')
