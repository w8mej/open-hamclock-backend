#!/usr/bin/perl
use strict;
use warnings;
use LWP::UserAgent;
use XML::RSS;
use HTML::Entities;

binmode(STDOUT, ':encoding(UTF-8)');

my $issues_url = 'https://hamweekly.com/rss/issues.xml';

my $ua = LWP::UserAgent->new(
    timeout => 10,
    agent   => 'Mozilla/5.0',
);

# Fetch issues RSS
my $resp = $ua->get($issues_url);
die "ISSUES FETCH FAILED: " . $resp->status_line . "\n"
    unless $resp->is_success;

my $rss = XML::RSS->new;
$rss->parse($resp->decoded_content);

# Latest issue
my $item = $rss->{items}[0]
    or die "NO ISSUES FOUND\n";

my $issue_url = $item->{link} || $item->{guid}
    or die "NO ISSUE URL\n";

# Fetch issue HTML
my $issue_resp = $ua->get($issue_url);
die "ISSUE FETCH FAILED: " . $issue_resp->status_line . "\n"
    unless $issue_resp->is_success;

my $html = $issue_resp->decoded_content;

# Extract article titles
while ($html =~ m{
    <span\s+class="archive-headline">
    \s*<a[^>]*>
    (.*?)
    </a>
    \s*</span>
}gxis) {
    my $title = $1;
    $title =~ s/<[^>]+>//g;
    decode_entities($title);
    $title =~ s/\s+$//;

    print "HamWeekly.com: $title\n";
}

