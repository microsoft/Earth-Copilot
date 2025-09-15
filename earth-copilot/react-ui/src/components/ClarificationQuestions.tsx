// Copyright (c) Microsoft Corporation.
// Licensed under the MIT license.

import React, { useState } from 'react';

interface ClarificationQuestionsProps {
  questions: string[];
  originalQuery: string;
  onAnswersSubmitted: (refinedQuery: string) => void;
  onSkip: () => void;
}

const ClarificationQuestions: React.FC<ClarificationQuestionsProps> = ({
  questions,
  originalQuery,
  onAnswersSubmitted,
  onSkip
}) => {
  const [answers, setAnswers] = useState<string[]>(new Array(questions.length).fill(''));
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleAnswerChange = (index: number, value: string) => {
    const newAnswers = [...answers];
    newAnswers[index] = value;
    setAnswers(newAnswers);
  };

  const handleSubmit = () => {
    setIsSubmitting(true);
    
    // Create a refined query by combining the original query with answers
    const answeredQuestions = questions
      .map((question, index) => answers[index] ? `${question}: ${answers[index]}` : '')
      .filter(Boolean);
    
    const refinedQuery = answeredQuestions.length > 0 
      ? `${originalQuery}. Additional details: ${answeredQuestions.join(', ')}`
      : originalQuery;
    
    onAnswersSubmitted(refinedQuery);
  };

  const handleSkip = () => {
    onSkip();
  };

  const hasAnswers = answers.some(answer => answer.trim().length > 0);

  return (
    <div className="clarification-questions-container bg-blue-50 border border-blue-200 rounded-lg p-4 my-4">
      <div className="flex items-start space-x-3">
        <div className="flex-shrink-0">
          <svg className="w-6 h-6 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        </div>
        <div className="flex-1">
          <h3 className="text-lg font-medium text-blue-900 mb-2">
            I need a bit more information to better help you
          </h3>
          <p className="text-blue-700 mb-4">
            Please provide additional details to refine your search:
          </p>
          
          <div className="space-y-3">
            {questions.map((question, index) => (
              <div key={index} className="flex flex-col">
                <label className="text-sm font-medium text-blue-800 mb-1">
                  {question}
                </label>
                <input
                  type="text"
                  value={answers[index]}
                  onChange={(e) => handleAnswerChange(index, e.target.value)}
                  placeholder="Enter your answer (optional)"
                  className="px-3 py-2 border border-blue-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                />
              </div>
            ))}
          </div>
          
          <div className="flex space-x-3 mt-4">
            <button
              onClick={handleSubmit}
              disabled={isSubmitting}
              className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isSubmitting ? 'Refining Search...' : hasAnswers ? 'Refine Search' : 'Search As-Is'}
            </button>
            <button
              onClick={handleSkip}
              className="px-4 py-2 bg-gray-500 text-white rounded-md hover:bg-gray-600 focus:outline-none focus:ring-2 focus:ring-gray-500 focus:ring-offset-2"
            >
              Continue with Original Query
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ClarificationQuestions;
