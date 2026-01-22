import React from 'react'
import { Link } from 'react-router-dom'
import './HomePage.css'

function HomePage() {
  return (
    <div className="homepage">
      <div className="homepage-layout">
        <div className="left-column">
          <aside className="resume-sidebar">
            <ul className="sidebar-links">
              <li>
                <a href="/documents/Transcript_Mason_Lancellotti.pdf" target="_blank" rel="noopener noreferrer">
                  Transcript
                </a>
              </li>
              <li>
                <a href="/documents/SAT_Mason_Lancellotti.pdf" target="_blank" rel="noopener noreferrer">
                  SAT Score
                </a>
              </li>
              <li>
                <a href="https://rbmediaglobal.com/" target="_blank" rel="noopener noreferrer">
                  RBmedia
                </a>
              </li>
              <li>
                <a href="https://my.lifetime.life/clubs/va/gainesville/programs/swim.html" target="_blank" rel="noopener noreferrer">
                  Life Time Fitness
                </a>
              </li>
              <li>
                <a href="https://www.mathnasium.com/math-centers/haymarket" target="_blank" rel="noopener noreferrer">
                  Mathnasium
                </a>
              </li>
              <li>
                <a href="https://economics.emory.edu/undergraduate/econ-dept-opportunities/tutoring.html" target="_blank" rel="noopener noreferrer">
                  Emory Economics Tutoring
                </a>
              </li>
              <li>
                <a href="https://emoryeconomicsreview.org/" target="_blank" rel="noopener noreferrer">
                  Emory Economics Review
                </a>
              </li>
            </ul>
          </aside>
          
          <div className="left-column-cards">
            <div className="right-panel-card right-panel-contact-card">
              <h3 className="right-panel-title">Contact</h3>
              <div className="right-panel-contact-container">
                <div className="right-panel-contact">
                  <span className="right-panel-contact-label">Email:</span>
                  <a href="mailto:malance@emory.edu" className="right-panel-contact-link">
                    malance@emory.edu
                  </a>
                </div>
                <div className="right-panel-contact">
                  <span className="right-panel-contact-label">Phone:</span>
                  <a href="tel:+17039193319" className="right-panel-contact-link">
                    (703) 919-3319
                  </a>
                </div>
              </div>
            </div>
            
            <div className="right-panel-card">
              <h3 className="right-panel-title">Links</h3>
              <div className="right-panel-links">
                <a href="/documents/Resume_Mason_Lancellotti.pdf" download="Resume_Mason_Lancellotti.pdf" className="right-panel-link">
                  Resume Download
                </a>
                <Link to="/tradingalgos" className="right-panel-link">
                  Trading Algorithms
                </Link>
                <a href="https://www.linkedin.com/in/masonlancellotti/" target="_blank" rel="noopener noreferrer" className="right-panel-link">
                  LinkedIn
                </a>
                <a href="https://github.com/masonlancellotti" target="_blank" rel="noopener noreferrer" className="right-panel-link">
                  GitHub
                </a>
              </div>
            </div>
          </div>
        </div>
        <div className="resume-container">
        <section className="resume-section">
          <h2 className="section-title">EDUCATION</h2>
          <div className="resume-item">
            <div className="item-header">
              <div>
                <h3 className="item-title">Emory University</h3>
                <p className="item-subtitle">BA in Economics and Computer Science, Minor in Business</p>
              </div>
              <div className="item-meta">
                <span className="item-location">Atlanta, GA</span>
                <span className="item-date">May 2027</span>
              </div>
            </div>
            <ul className="item-bullets">
              <li>
                <a href="/documents/Transcript_Mason_Lancellotti.pdf" target="_blank" rel="noopener noreferrer" className="gpa-link">
                  Cumulative GPA: 3.99 / 4.00
                </a>
              </li>
              <li>Honors: Dean's List (3x)</li>
              <li>
                <a href="/documents/SAT_Mason_Lancellotti.pdf" target="_blank" rel="noopener noreferrer" className="gpa-link">
                  SAT Score: 1570
                </a>
              </li>
            </ul>
          </div>
        </section>

        <section className="resume-section">
          <h2 className="section-title">PROFESSIONAL EXPERIENCE</h2>
          
          <div className="resume-item">
            <div className="item-header">
              <div>
                <h3 className="item-title">
                  <a href="https://rbmediaglobal.com/" target="_blank" rel="noopener noreferrer" className="company-link">
                    RBmedia
                  </a>
                </h3>
                <p className="item-subtitle">Marketing Intern</p>
              </div>
              <div className="item-meta">
                <span className="item-location">Landover, MD</span>
                <span className="item-date">June 2025 – Aug 2025</span>
              </div>
            </div>
            <ul className="item-bullets">
              <li>Compiled monthly and quarterly reports on Audible and Spotify audiobook sales for 2,500+ titles; visualized data using tables and graphs which highlighted key trends and considered different perspectives to help guide future executive decision-making</li>
              <li>Assisted in rollout of an automated workflow for posting audiobook sneak-peeks across 12 social media accounts; supervised the first ~1,800 uploads, diagnosing and resolving technical issues in real time to improve scalability and reliability over time</li>
            </ul>
          </div>

          <div className="resume-item">
            <div className="item-header">
              <div>
                <h3 className="item-title">
                  <a href="https://my.lifetime.life/clubs/va/gainesville/programs/swim.html" target="_blank" rel="noopener noreferrer" className="company-link">
                    Life Time Fitness
                  </a>
                </h3>
                <p className="item-subtitle">Lifeguard</p>
              </div>
              <div className="item-meta">
                <span className="item-location">Gainesville, VA</span>
                <span className="item-date">May 2024 – Aug 2025</span>
              </div>
            </div>
            <ul className="item-bullets">
              <li>Supervised aquatics patrons by monitoring pool activities and proactively enforcing guidelines to prevent accidents; delivered prompt emergency response and administered first aid on 4 separate occasions, communicating directly with police and EMS</li>
              <li>Collaborated with management and other departments on events involving aquatics programs; provided exceptional customer service to 300+ members daily, promptly resolving issues and concerns to maintain consistently positive facility experiences</li>
            </ul>
          </div>

          <div className="resume-item">
            <div className="item-header">
              <div>
                <h3 className="item-title">
                  <a href="https://www.mathnasium.com/math-centers/haymarket" target="_blank" rel="noopener noreferrer" className="company-link">
                    Mathnasium
                  </a>
                </h3>
                <p className="item-subtitle">Math Instructor</p>
              </div>
              <div className="item-meta">
                <span className="item-location">Haymarket, VA</span>
                <span className="item-date">June 2022 – Mar 2023</span>
              </div>
            </div>
            <ul className="item-bullets">
              <li>Taught mathematics to 30+ K-12 students, assisting them through structured learning activities and providing homework help; introduced effective study techniques and problem-solving strategies to improve students' retention and academic confidence</li>
              <li>Communicated regularly with parents, providing feedback on student progress and setbacks; developed personalized learning plans, resulting in approximately 90% of students reporting higher grades and demonstrating improved critical-thinking skills</li>
            </ul>
          </div>
        </section>

        <section className="resume-section">
          <h2 className="section-title">LEADERSHIP EXPERIENCE</h2>
          
          <div className="resume-item">
            <div className="item-header">
              <div>
                <h3 className="item-title">
                  <a href="https://economics.emory.edu/undergraduate/econ-dept-opportunities/tutoring.html" target="_blank" rel="noopener noreferrer" className="company-link">
                    Emory Economics Department
                  </a>
                </h3>
                <p className="item-subtitle">Student Tutor</p>
              </div>
              <div className="item-meta">
                <span className="item-location">Atlanta, GA</span>
                <span className="item-date">Sept 2025 – Present</span>
              </div>
            </div>
            <ul className="item-bullets">
              <li>Selected as 1 of 60 from ~800 students to offer one-on-one instruction in micro/macroeconomics, data science, and computer science; develop comprehensive review guides and utilize syllabi to create exam-based timelines with regular progress checks</li>
              <li>Conduct 3-5 sessions per week focused on content mastery, correcting mistakes and misconceptions, problem set completion, and test strategy and preparation; correspond with professors and teaching assistants when needed to clarify solution methods</li>
            </ul>
          </div>

          <div className="resume-item">
            <div className="item-header">
              <div>
                <h3 className="item-title">
                  Emory Club Swimming
                </h3>
                <p className="item-subtitle">Head Captain</p>
              </div>
              <div className="item-meta">
                <span className="item-location">Atlanta, GA</span>
                <span className="item-date">Jan 2024 – Present</span>
              </div>
            </div>
            <ul className="item-bullets">
              <li>Design and lead practices with 10-20 swimmers 4 times per week; utilize a combination of technique work for new swimmers and endurance training for more experienced swimmers, ensuring that sessions are balanced to accommodate every skill level</li>
              <li>Collaborate with other board members and club sports directors to coordinate logistics for team travel, including 6 out-of-state meets requiring detailed planning, budgeting, and communication; manage itineraries, preparation, lodging, and transportation</li>
            </ul>
          </div>
        </section>

        <section className="resume-section">
          <h2 className="section-title">ORGANIZATIONS</h2>
          <div className="resume-item">
            <p><strong>Professional:</strong> Omicron Delta Epsilon (International Economics Honor Society)</p>
            <p><strong>Clubs:</strong> <a href="https://emoryeconomicsreview.org/" target="_blank" rel="noopener noreferrer" className="company-link">Emory Economics Review</a>, Emory Economics Investment Forum, Emory Computer Science Club</p>
          </div>
        </section>

        <section className="resume-section">
          <h2 className="section-title">ADDITIONAL INFORMATION</h2>
          <div className="resume-item">
            <p><strong>Skills:</strong> Expert in Python, Excel, AI tools, PowerPoint; Advanced in Java, statistical modeling, corporate finance; Proficient in SQL, JavaScript, HTML web development, accounting; Intermediate in Tableau, API integration, web scraping; Elementary in Power BI, R</p>
            <p><strong>Languages:</strong> Proficient in Spanish</p>
            <p><strong>Interests:</strong> Weightlifting, investing, pickleball, travel, football, biohacking, singing, medieval history</p>
          </div>
        </section>
        </div>
        <aside className="right-panel">
          <div className="right-panel-card">
            <h3 className="right-panel-title">About</h3>
            <p className="right-panel-text">
              I'm Mason Lancellotti, a junior at Emory University. I'm particularly passionate about investing, finance, and data analytics. During my last semester, I expanded my economic modeling abilities and learned the fundamentals of AI to improve work efficiency. This semester, I am focused specifically on computer science and business, in order to bolster my technical skills further and gain a more analytical perspective behind how firms operate and make decisions.
            </p>
          </div>
          
          <div className="right-panel-card">
            <h3 className="right-panel-title">What I'm Looking For</h3>
            <p className="right-panel-text">
              Seeking Summer 2026 internships in wealth management, consulting, or data analytics. Interested in roles that will allow me to utilize my unique, interdisciplinary background to have a meaningful impact on the business, clients, or the world.
            </p>
            <ul className="right-panel-list">
              <li>Preferred Locations: DMV, Atlanta, NYC</li>
            </ul>
          </div>
          
          <div className="right-panel-card">
            <h3 className="right-panel-title">What I'm Working On</h3>
            <ul className="right-panel-list">
              <li>Website bug fixes/improvements and adding mobile compatibility</li>
              <li>Building a third trading program for stock options using the Black-Scholes model</li>
              <li>Observing the current trading algorithms' performance and changing them accordingly</li>
            </ul>
          </div>
        </aside>
      </div>
    </div>
  )
}

export default HomePage

