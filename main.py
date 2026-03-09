from fsrs import Scheduler, Card, Rating
from datetime import datetime, timezone

if __name__ == '__main__':
    scheduler = Scheduler()
    card = Card()
     
    # new cards are to be reviewd immediately
    delta = card.due - datetime.now(timezone.utc)
    print(f"Card due in {delta.seconds} seconds")

    # show question... 
    # show answer... 
    # ask for rating... 
    rating = Rating.Good
    card, log = scheduler.review_card(card, rating)
    print(f"Card rated {log.rating} at {log.review_datetime}")

    # how much time between when the card is due and now
    delta = card.due - datetime.now(timezone.utc)
    print(f"Card due in {delta.seconds} seconds")
